from nipype.interfaces.base import (
    CommandLine,
    BaseInterface,
    BaseInterfaceInputSpec,
    CommandLineInputSpec,
    TraitedSpec,
    File,
    traits, isdefined,
)
import os
import nibabel as nib
from skimage.filters import threshold_yen
from scipy.ndimage import binary_closing, binary_fill_holes
from skimage import measure
import vtk
from vtkmodules.util import numpy_support
import math
import numpy as np
from scipy.ndimage import binary_dilation, generate_binary_structure

class SegmentEndocraniumInputSpec(BaseInterfaceInputSpec):

    slicer_cmd = File(
        exists=True,
        mandatory=True,
        desc="Slicer executable path"
    )

    in_file = File(
        exists=True,
        mandatory=True,
        desc="Original CT image",
    )

    out_file = File(
        desc="Endocranium mask file name",
        genfile=True
    )

    smoothingKernelSize = traits.Float(
        3.0,
        usedefault=True,
        desc="Kernel size in mm",
    )

    oversampling = traits.Float(
        1.0,
        usedefault=True,
        desc="Wrap solidify oversampling",
    )

    iterations = traits.Int(
        3,
        usedefault=True,
        desc="Shrinkwrap iterations",
    )


class SegmentEndocraniumOutputSpec(TraitedSpec):
    out_file = File(
        exists=True,
        desc="Endocranium mask"
    )


class SegmentEndocranium(BaseInterface):
    input_spec = SegmentEndocraniumInputSpec
    output_spec = SegmentEndocraniumOutputSpec

    @staticmethod
    def _polydata_to_labelmap(polydata, spacing=1.0, extra_margin_to_bounds=0, reference_image=None):

        binary_labelmap = vtk.vtkImageData()

        if reference_image:
            origin = reference_image.GetOrigin()
            spacing3 = reference_image.GetSpacing()
            extent = reference_image.GetExtent()
        else:
            bounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            polydata.GetBounds(bounds)
            bounds[0] -= extra_margin_to_bounds
            bounds[2] -= extra_margin_to_bounds
            bounds[4] -= extra_margin_to_bounds
            bounds[1] += extra_margin_to_bounds
            bounds[3] += extra_margin_to_bounds
            bounds[5] += extra_margin_to_bounds

            spacing3 = np.ones(3) * spacing
            dim = [0, 0, 0]
            for i in range(3):
                # Add 3 to the dimensions to have at least 1 voxel thickness and 1 voxel margin on both sides
                dim[i] = int(math.ceil((bounds[i * 2 + 1] - bounds[i * 2]) / spacing3[i])) + 3

            # Subtract one spacing to ensure there is a margin
            origin = [
                bounds[0] - spacing3[0],
                bounds[2] - spacing3[1],
                bounds[4] - spacing3[2]]

            extent = [0, dim[0] - 1, 0, dim[1] - 1, 0, dim[2] - 1]

        binary_labelmap.SetOrigin(origin)
        binary_labelmap.SetSpacing(spacing3)
        binary_labelmap.SetExtent(extent)

        binary_labelmap.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
        binary_labelmap.GetPointData().GetScalars().Fill(0)

        pol2stenc = vtk.vtkPolyDataToImageStencil()
        pol2stenc.SetInputData(polydata)
        pol2stenc.SetOutputOrigin(origin)
        pol2stenc.SetOutputSpacing(spacing3)
        pol2stenc.SetOutputWholeExtent(binary_labelmap.GetExtent())

        imgstenc = vtk.vtkImageStencil()
        imgstenc.SetInputData(binary_labelmap)
        imgstenc.SetStencilConnection(pol2stenc.GetOutputPort())
        imgstenc.ReverseStencilOn()
        imgstenc.SetBackgroundValue(1)
        imgstenc.Update()

        return imgstenc.GetOutput()

    @staticmethod
    def _labelmap_to_polydata(labelmap, value=1):
        discrete_cubes = vtk.vtkDiscreteMarchingCubes()
        discrete_cubes.SetInputData(labelmap)
        discrete_cubes.SetValue(0, value)

        reverse = vtk.vtkReverseSense()
        reverse.SetInputConnection(discrete_cubes.GetOutputPort())
        reverse.ReverseCellsOn()
        reverse.ReverseNormalsOn()
        reverse.Update()

        return reverse.GetOutput()

    @staticmethod
    def _remesh_polydata(polydata, spacing):
        labelmap = SegmentEndocranium._polydata_to_labelmap(polydata, spacing)
        return SegmentEndocranium._labelmap_to_polydata(labelmap)

    def _shrink_wrap(self, region_pd, input_spacing, input_pd, iterations=None):
        """
        Simula il filtro Shrinkwrap di Slicer:
        - region_pd: mesh iniziale da smussare
        - input_pd: mesh vincolo (input originale)
        - input_spacing: scala voxel per oversampling
        - iterations: numero iterazioni di shrinkwrap (default: self.inputs.iterations)
        """
        if iterations is None:
            iterations = self.inputs.iterations

        spacing = input_spacing / self.inputs.oversampling

        # Copia della mesh iniziale
        smoothed = vtk.vtkPolyData()
        smoothed.DeepCopy(region_pd)

        # Locator per punti più vicini sulla mesh originale
        locator = vtk.vtkPointLocator()
        locator.SetDataSet(input_pd)
        locator.BuildLocator()

        for it in range(iterations):
            if smoothed.GetNumberOfPoints() <= 1 or input_pd.GetNumberOfPoints() <= 1:
                raise ValueError("Mesh vuota durante shrink-wrap")

            # 1️⃣ Smoothing semplice
            smoother = vtk.vtkSmoothPolyDataFilter()
            smoother.SetInputData(smoothed)
            smoother.FeatureEdgeSmoothingOff()
            smoother.BoundarySmoothingOff()
            smoother.Update()
            smoothed.DeepCopy(smoother.GetOutput())

            # 2️⃣ Vincolo punti alla mesh originale
            points = smoothed.GetPoints()
            for pid in range(points.GetNumberOfPoints()):
                pt = np.array(points.GetPoint(pid))
                closest_id = locator.FindClosestPoint(pt)
                closest_pt = np.array(input_pd.GetPoint(closest_id))
                new_pt = pt * (1 - relaxation) + closest_pt * relaxation
                points.SetPoint(pid, new_pt.tolist())
            points.Modified()

            # 3️⃣ (Opzionale) remesh per uniformità voxel
            remeshed = SegmentEndocranium._remesh_polydata(smoothed, spacing)
            smoothed.DeepCopy(remeshed)

        return smoothed

    def _get_initial_region_pd(self, input_spacing, input_pd):
        """Get initial shape that will be snapped to closest point of the input segment"""

        spacing = input_spacing / self.inputs.oversampling

        # create sphere that encloses entire segment content
        bounds = np.zeros(6)
        input_pd.GetBounds(bounds)
        diameters = np.array([bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]])
        max_radius = max(diameters) / 2.0
        sphere_source = vtk.vtkSphereSource()
        # to make sure the volume is fully included in the sphere, radius must be sqrt(2) times larger
        sphere_source.SetRadius(max_radius * 1.5)

        # Set resolution to be about one magnitude lower than the final resolution
        # (by creating an initial surface element for about every 100th final element).
        sphere_surface_area = 4 * math.pi * max_radius * max_radius
        voxel_surface_area = spacing * spacing
        number_of_surface_elements = sphere_surface_area / voxel_surface_area
        number_of_initial_sphere_surface_elements = number_of_surface_elements / 100
        sphere_resolution = math.sqrt(number_of_initial_sphere_surface_elements)
        # Set resolution to minimum 10
        sphere_resolution = max(int(sphere_resolution), 10)
        sphere_source.SetPhiResolution(sphere_resolution)
        sphere_source.SetThetaResolution(sphere_resolution)
        sphere_source.SetCenter((bounds[0] + bounds[1]) / 2.0, (bounds[2] + bounds[3]) / 2.0,
                               (bounds[4] + bounds[5]) / 2.0)
        sphere_source.Update()
        initial_region_pd = sphere_source.GetOutput()
        clean_poly_data = vtk.vtkCleanPolyData()
        clean_poly_data.SetInputData(initial_region_pd)
        clean_poly_data.Update()
        initial_region_pd = clean_poly_data.GetOutput()
        return initial_region_pd

    @staticmethod
    def update_input_pd_from_binary(binary_map, spacing):
        """
        Replicates Slicer _updateInputPd in Python:
        - creates a closed surface (_inputPd)
        - computes inputSpacing

        Parameters
        ----------
        binary_map : np.ndarray
            3D binary mask
        spacing : tuple
            voxel spacing (sx, sy, sz) in mm

        Returns
        -------
        _inputPd : vtk.vtkPolyData
            Closed surface of the binary mask
        _inputSpacing : float
            Diagonal of voxel spacing
        """

        # ---------------------------
        # 1. Cast to boolean
        # ---------------------------
        mask = binary_map > 0
        if not np.any(mask):
            raise ValueError("Input binary map is empty")

        # ---------------------------
        # 2. Create surface with marching cubes
        # ---------------------------
        verts, faces, normals, values = measure.marching_cubes(
            mask.astype(np.float32), level=0.5, spacing=spacing
        )

        # ---------------------------
        # 3. Convert to vtkPolyData
        # ---------------------------
        points = vtk.vtkPoints()
        for v in verts:
            points.InsertNextPoint(v[0], v[1], v[2])

        polys = vtk.vtkCellArray()
        for f in faces:
            triangle = vtk.vtkTriangle()
            triangle.GetPointIds().SetId(0, f[0])
            triangle.GetPointIds().SetId(1, f[1])
            triangle.GetPointIds().SetId(2, f[2])
            polys.InsertNextCell(triangle)

        _inputPd = vtk.vtkPolyData()
        _inputPd.SetPoints(points)
        _inputPd.SetPolys(polys)

        # ---------------------------
        # 4. Compute inputSpacing
        # ---------------------------
        _inputSpacing = np.linalg.norm(spacing)

        return _inputPd, _inputSpacing

    @staticmethod
    def extend_binary_labelmap(binary_map, input_spacing, split_cavities_radius):
        """
        Replicates vtkITKImageMargin in Python
        by dilating a binary map by splitCavitiesDiameter/2 in mm.

        Parameters
        ----------
        binary_map : np.ndarray
            Input binary map (0/1)
        input_spacing : tuple of float
            Voxel spacing (sx, sy, sz) in mm
        split_cavities_radius : float
            Radius in mm for margin

        Returns
        -------
        extended : np.ndarray
            Extended labelmap (0/255)
        """

        # ---------------------------
        # 2. Convert radius mm -> voxel for each dimension
        # ---------------------------
        radius_voxel = [int(np.ceil(split_cavities_radius / s)) for s in input_spacing]

        # ---------------------------
        # 3. Create structuring element
        # ---------------------------
        # Generate a cuboid structure of size (2*radius+1)
        structure = generate_binary_structure(3, 1)  # connectivity 1
        structure = np.pad(structure,
                           pad_width=[(radius_voxel[0], radius_voxel[0]),
                                      (radius_voxel[1], radius_voxel[1]),
                                      (radius_voxel[2], radius_voxel[2])],
                           mode='constant', constant_values=0)

        # ---------------------------
        # 4. Dilate
        # ---------------------------
        dilated = binary_dilation(binary_map, structure=structure)

        # ---------------------------
        # 5. Convert to 0/255
        # ---------------------------
        extended = np.zeros_like(dilated, dtype=np.uint8)
        extended[dilated] = 255

        return extended

    @staticmethod
    def vtk_to_numpy_image(vtk_image):
        """Convert vtkImageData (scalar) to numpy 3D array"""
        dims = vtk_image.GetDimensions()  # (x, y, z)
        scalars = vtk_image.GetPointData().GetScalars()
        np_array = numpy_support.vtk_to_numpy(scalars)
        np_array = np_array.reshape(dims[2], dims[1], dims[0])  # VTK: z,y,x order
        np_array = np_array.transpose(2, 1, 0)  # reorder to x,y,z
        return np_array

    @staticmethod
    def numpy_to_vtk_image(np_array, reference_vtk):
        """Convert numpy 3D array to vtkImageData, copying spacing/origin from reference"""
        np_array = np_array.transpose(2, 1, 0)  # x,y,z -> z,y,x
        flat = np_array.ravel()
        vtk_array = numpy_support.numpy_to_vtk(num_array=flat, deep=True, array_type=vtk.VTK_UNSIGNED_CHAR)

        img = vtk.vtkImageData()
        img.DeepCopy(reference_vtk)
        img.GetPointData().SetScalars(vtk_array)
        return img

    def _extract_cavity(self, shrunken_pd, input_spacing, input_pd, spacing_tuple):
        """
        Estrae la cavità interna più grande a partire da una mesh shrunken_pd.
        """
        spacing = input_spacing / self.inputs.oversampling

        # 1Converti la mesh "shrunken" in labelmap (0=outside, 1=inside)
        outside_labelmap = SegmentEndocranium._polydata_to_labelmap(shrunken_pd, spacing)

        # Converti la mesh originale in labelmap, stessa estensione
        input_labelmap = SegmentEndocranium._polydata_to_labelmap(input_pd, reference_image=outside_labelmap)
        input_labelmap_np = SegmentEndocranium.vtk_to_numpy_image(input_labelmap)

        # Dilata la maschera per colmare piccoli gap
        split_cavities_radius = 7.5  # raggio mm = metà diametro desiderato
        extended_np = self.extend_binary_labelmap(input_labelmap_np, spacing_tuple, split_cavities_radius)

        # Converti a vtk
        extended_vtk = SegmentEndocranium.numpy_to_vtk_image(extended_np, input_labelmap)

        # Inverti la maschera (0=cavità interna, 1=fuori)
        inverter = vtk.vtkImageThreshold()
        inverter.SetInputData(outside_labelmap)
        inverter.ThresholdByLower(0)
        inverter.SetInValue(1)  # background
        inverter.SetOutValue(0)  # cavità
        inverter.SetOutputScalarType(vtk.VTK_UNSIGNED_CHAR)
        inverter.Update()
        inverted_labelmap = inverter.GetOutput()

        # Combina con la maschera dilatata
        combiner = vtk.vtkImageMathematics()
        combiner.SetInput1Data(inverted_labelmap)
        combiner.SetInput2Data(extended_vtk)
        combiner.SetOperationToMax()
        combiner.Update()
        combined_labelmap = combiner.GetOutput()

        # Estrai la cavità più grande
        conn_filter = vtk.vtkImageConnectivityFilter()
        conn_filter.SetExtractionModeToLargestRegion()
        conn_filter.SetScalarRange(1, 1)  # seleziona la cavità (0)
        conn_filter.SetInputData(combined_labelmap)
        conn_filter.Update()
        largest_hole_labelmap = conn_filter.GetOutput()

        # Converti di nuovo in polydata
        cavity_pd = SegmentEndocranium._labelmap_to_polydata(largest_hole_labelmap, value=0)

        # Applica shrinkwrap sulla cavità
        return self._shrink_wrap(cavity_pd, input_spacing, input_pd)

    @staticmethod
    def _smooth_polydata(polydata, smoothing_factor):
        pass_band = pow(10.0, -4.0 * smoothing_factor)
        smoother_sinc = vtk.vtkWindowedSincPolyDataFilter()
        smoother_sinc.SetInputData(polydata)
        smoother_sinc.SetNumberOfIterations(20)
        smoother_sinc.FeatureEdgeSmoothingOff()
        smoother_sinc.BoundarySmoothingOff()
        smoother_sinc.NonManifoldSmoothingOn()
        smoother_sinc.NormalizeCoordinatesOn()
        smoother_sinc.Update()
        return smoother_sinc.GetOutput()

    @staticmethod
    def _align_polydata_to_reference(polydata, reference_vtk):
        """
        Trasla la mesh (polydata) in modo che coincida con l'origine del reference VTK.
        """
        origin = np.array(reference_vtk.GetOrigin())
        # il polydata ha origine (0,0,0) -> trasla verso origin
        transform = vtk.vtkTransform()
        transform.Translate(origin)

        transform_filter = vtk.vtkTransformPolyDataFilter()
        transform_filter.SetInputData(polydata)
        transform_filter.SetTransform(transform)
        transform_filter.Update()

        aligned_pd = vtk.vtkPolyData()
        aligned_pd.DeepCopy(transform_filter.GetOutput())
        return aligned_pd

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        kernel_size_mm = self.inputs.smoothingKernelSize

        # =========================
        # 1. CARICA NIFTI
        # =========================
        nii = nib.load(self.inputs.in_file)
        img = nii.get_fdata().astype(np.float32)

        # =========================
        # 2. MAXIMUM ENTROPY THRESHOLD
        # =========================
        foreground = img[img > 0]
        threshold = threshold_yen(foreground)
        print(f"Maximum Entropy threshold: {threshold}")

        # =========================
        # 3. MASCHERA BINARIA
        # =========================
        binary = (img > threshold) & (img > 0)

        # =========================
        # 4. KERNEL MORFOLOGICO (mm → voxel)
        # =========================
        spacing_tuple = tuple(nii.header.get_zooms()[:3])
        kernel_size_voxel = [
            int(round((kernel_size_mm / spacing_tuple[i] + 1) / 2) * 2 - 1)
            for i in range(3)
        ]
        kernel_size_voxel = [k if k % 2 == 1 else k + 1 for k in kernel_size_voxel]
        structure = np.ones(kernel_size_voxel, dtype=bool)

        # =========================
        # 5. CLOSING MORFOLOGICO
        # =========================
        binary_smoothed = binary_closing(binary, structure=structure)
        binary_smoothed = binary_fill_holes(binary_smoothed)

        # =========================
        # 6. CONVERTI LA MASCHERA IN VTK (riferimento)
        # =========================
        binary_smoothed_vtk = vtk.vtkImageData()
        dims = binary_smoothed.shape
        binary_flat = binary_smoothed.ravel().astype(np.uint8)
        vtk_array = numpy_support.numpy_to_vtk(binary_flat, deep=True, array_type=vtk.VTK_UNSIGNED_CHAR)
        binary_smoothed_vtk.SetDimensions(dims[::-1])  # VTK: x,y,z
        binary_smoothed_vtk.SetSpacing(spacing_tuple)
        binary_smoothed_vtk.SetOrigin(nii.affine[:3, 3])  # origine dal NIfTI
        binary_smoothed_vtk.GetPointData().SetScalars(vtk_array)

        # =========================
        # 7. POLYDATA DALLA MASCHERA
        # =========================
        input_pd, input_spacing = self.update_input_pd_from_binary(binary_smoothed, spacing_tuple)
        region_pd = self._get_initial_region_pd(input_spacing, input_pd)

        shrunken_pd = self._shrink_wrap(region_pd, input_spacing, input_pd)
        shrunken_pd = self._extract_cavity(shrunken_pd, input_spacing, input_pd, spacing_tuple)
        shrunken_pd = SegmentEndocranium._smooth_polydata(shrunken_pd, 0.2)

        # =========================
        # 8. CONVERTI DI NUOVO IN VTK LABELMAP ALLINEATA
        # =========================
        shrunken_pd_aligned = self._align_polydata_to_reference(shrunken_pd, binary_smoothed_vtk)

        shrunken_labelmap = SegmentEndocranium._polydata_to_labelmap(
            shrunken_pd_aligned, reference_image=binary_smoothed_vtk
        )

        shrunken_labelmap_np = SegmentEndocranium.vtk_to_numpy_image(shrunken_labelmap)

        # =========================
        # 9. SALVA NIFTI
        # =========================
        out = nib.Nifti1Image(shrunken_labelmap_np.astype(np.uint8), affine=nii.affine)
        nib.save(out, self.inputs.out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "cropped_" + os.path.basename(self.inputs.in_file)
        return os.path.abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs



