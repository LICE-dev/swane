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
    def _polydataToLabelmap(polydata, spacing=1.0, extraMarginToBounds=0, referenceImage=None):

        binaryLabelmap = vtk.vtkImageData()

        if referenceImage:
            origin = referenceImage.GetOrigin()
            spacing3 = referenceImage.GetSpacing()
            extent = referenceImage.GetExtent()
        else:
            bounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            polydata.GetBounds(bounds)
            bounds[0] -= extraMarginToBounds
            bounds[2] -= extraMarginToBounds
            bounds[4] -= extraMarginToBounds
            bounds[1] += extraMarginToBounds
            bounds[3] += extraMarginToBounds
            bounds[5] += extraMarginToBounds

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

        binaryLabelmap.SetOrigin(origin)
        binaryLabelmap.SetSpacing(spacing3)
        binaryLabelmap.SetExtent(extent)

        binaryLabelmap.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
        binaryLabelmap.GetPointData().GetScalars().Fill(0)

        pol2stenc = vtk.vtkPolyDataToImageStencil()
        pol2stenc.SetInputData(polydata)
        pol2stenc.SetOutputOrigin(origin)
        pol2stenc.SetOutputSpacing(spacing3)
        pol2stenc.SetOutputWholeExtent(binaryLabelmap.GetExtent())

        imgstenc = vtk.vtkImageStencil()
        imgstenc.SetInputData(binaryLabelmap)
        imgstenc.SetStencilConnection(pol2stenc.GetOutputPort())
        imgstenc.ReverseStencilOn()
        imgstenc.SetBackgroundValue(1)
        imgstenc.Update()

        return imgstenc.GetOutput()

    @staticmethod
    def _labelmapToPolydata(labelmap, value=1):
        discreteCubes = vtk.vtkDiscreteMarchingCubes()
        discreteCubes.SetInputData(labelmap)
        discreteCubes.SetValue(0, value)

        reverse = vtk.vtkReverseSense()
        reverse.SetInputConnection(discreteCubes.GetOutputPort())
        reverse.ReverseCellsOn()
        reverse.ReverseNormalsOn()
        reverse.Update()

        return reverse.GetOutput()

    @staticmethod
    def _remeshPolydata(polydata, spacing):
        labelmap = SegmentEndocranium._polydataToLabelmap(polydata, spacing)
        return SegmentEndocranium._labelmapToPolydata(labelmap)

    def _shrinkWrap(self, regionPd, input_spacing, input_pd):

        shrunkenPd = regionPd
        spacing = input_spacing / self.inputs.oversampling

        for iterationIndex in range(self.inputs.iterations):
            if shrunkenPd.GetNumberOfPoints() <= 1 or input_pd.GetNumberOfPoints() <= 1:
                # we must not feed empty polydata into vtkSmoothPolyDataFilter because it would crash the application
                raise ValueError("Mesh has become empty during shrink-wrap iterations")
            smoothFilter = vtk.vtkSmoothPolyDataFilter()
            smoothFilter.SetInputData(0, shrunkenPd)
            smoothFilter.SetInputData(1, input_pd)  # constrain smoothed points to the input surface
            smoothFilter.Update()
            shrunkenPd = vtk.vtkPolyData()
            shrunkenPd.DeepCopy(smoothFilter.GetOutput())

            remeshedPd = SegmentEndocranium._remeshPolydata(shrunkenPd, spacing)
            shrunkenPd = vtk.vtkPolyData()
            shrunkenPd.DeepCopy(remeshedPd)

        return shrunkenPd

    def _getInitialRegionPd(self, input_spacing, input_pd):
        """Get initial shape that will be snapped to closest point of the input segment"""

        spacing = input_spacing / self.inputs.oversampling

        # create sphere that encloses entire segment content
        bounds = np.zeros(6)
        input_pd.GetBounds(bounds)
        diameters = np.array([bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]])
        maxRadius = max(diameters) / 2.0
        sphereSource = vtk.vtkSphereSource()
        # to make sure the volume is fully included in the sphere, radius must be sqrt(2) times larger
        sphereSource.SetRadius(maxRadius * 1.5)

        # Set resolution to be about one magnitude lower than the final resolution
        # (by creating an initial surface element for about every 100th final element).
        sphereSurfaceArea = 4 * math.pi * maxRadius * maxRadius
        voxelSurfaceArea = spacing * spacing
        numberOfSurfaceElements = sphereSurfaceArea / voxelSurfaceArea
        numberOfIinitialSphereSurfaceElements = numberOfSurfaceElements / 100
        sphereResolution = math.sqrt(numberOfIinitialSphereSurfaceElements)
        # Set resolution to minimum 10
        sphereResolution = max(int(sphereResolution), 10)
        sphereSource.SetPhiResolution(sphereResolution)
        sphereSource.SetThetaResolution(sphereResolution)
        sphereSource.SetCenter((bounds[0] + bounds[1]) / 2.0, (bounds[2] + bounds[3]) / 2.0,
                               (bounds[4] + bounds[5]) / 2.0)
        sphereSource.Update()
        initialRegionPd = sphereSource.GetOutput()
        cleanPolyData = vtk.vtkCleanPolyData()
        cleanPolyData.SetInputData(initialRegionPd)
        cleanPolyData.Update()
        initialRegionPd = cleanPolyData.GetOutput()
        return initialRegionPd

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
    def extend_binary_labelmap(binary_map, spacing, splitCavitiesDiameter):
        """
        Replicates vtkITKImageMargin in Python
        by dilating a binary map by splitCavitiesDiameter/2 in mm.

        Parameters
        ----------
        binary_map : np.ndarray
            Input binary map (0/1)
        spacing : tuple of float
            Voxel spacing (sx, sy, sz) in mm
        splitCavitiesDiameter : float
            Diameter in mm for margin

        Returns
        -------
        extended : np.ndarray
            Extended labelmap (0/255)
        """
        # ---------------------------
        # 1. Calculate radius in mm
        # ---------------------------
        splitCavitiesRadius = splitCavitiesDiameter / 2.0

        # ---------------------------
        # 2. Convert radius mm -> voxel for each dimension
        # ---------------------------
        radius_voxel = [int(np.ceil(splitCavitiesRadius / s)) for s in spacing]

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

    def _extractCavity(self, shrunkenPd, input_spacing, input_pd):

        spacing = input_spacing / self.inputs.oversampling
        outsideObjectLabelmap = SegmentEndocranium._polydataToLabelmap(shrunkenPd, spacing)  # 0=outside, 1=inside

        inputLabelmap = SegmentEndocranium._polydataToLabelmap(input_pd, referenceImage=outsideObjectLabelmap)
        inputLabelmap_np = SegmentEndocranium.vtk_to_numpy_image(inputLabelmap)

        splitCavitiesDiameter = 15

        # It is less accurate but more robust to dilate labelmap than grow polydata.
        # Since accuracy is not important here, we dilate labelmap.
        splitCavitiesRadius = splitCavitiesDiameter / 2.0
        # Dilate
        extendedInputLabelmap_np = self.extend_binary_labelmap(inputLabelmap_np, spacing, splitCavitiesRadius)
        extendedInputLabelmap = SegmentEndocranium.numpy_to_vtk_image(extendedInputLabelmap_np, inputLabelmap)

        outsideObjectLabelmapInverter = vtk.vtkImageThreshold()
        outsideObjectLabelmapInverter.SetInputData(outsideObjectLabelmap)
        outsideObjectLabelmapInverter.ThresholdByLower(0)
        outsideObjectLabelmapInverter.SetInValue(1)  # backgroundValue
        outsideObjectLabelmapInverter.SetOutValue(0)  # labelValue
        outsideObjectLabelmapInverter.SetOutputScalarType(outsideObjectLabelmap.GetScalarType())
        outsideObjectLabelmapInverter.Update()

        addImage = vtk.vtkImageMathematics()
        addImage.SetInput1Data(outsideObjectLabelmapInverter.GetOutput())
        addImage.SetInput2Data(extendedInputLabelmap)
        addImage.SetOperationToMax()
        addImage.Update()
        internalHolesLabelmap = addImage.GetOutput()
        # internal holes are 0, elsewhere >=1

        # Find largest internal hole
        largestHoleExtract = vtk.vtkImageConnectivityFilter()
        largestHoleExtract.SetScalarRange(-0.5, 0.5)
        largestHoleExtract.SetInputData(internalHolesLabelmap)
        largestHoleExtract.SetExtractionModeToLargestRegion()
        largestHoleExtract.Update()
        largestHolesLabelmap = largestHoleExtract.GetOutput()

        # Convert back to polydata
        initialRegionPd = vtk.vtkPolyData()
        initialRegionPd.DeepCopy(SegmentEndocranium._labelmapToPolydata(largestHolesLabelmap, 0))

        return self._shrinkWrap(initialRegionPd, input_spacing, input_pd)

    @staticmethod
    def _smoothPolydata(polydata, smoothingFactor):
        passBand = pow(10.0, -4.0 * smoothingFactor)
        smootherSinc = vtk.vtkWindowedSincPolyDataFilter()
        smootherSinc.SetInputData(polydata)
        smootherSinc.SetNumberOfIterations(20)
        smootherSinc.FeatureEdgeSmoothingOff()
        smootherSinc.BoundarySmoothingOff()
        smootherSinc.NonManifoldSmoothingOn()
        smootherSinc.NormalizeCoordinatesOn()
        smootherSinc.Update()
        return smootherSinc.GetOutput()

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        kernelSizeMm = self.inputs.smoothingKernelSize

        # =========================
        # 1. CARICA NIFTI
        # =========================
        nii = nib.load(self.inputs.in_file)
        img = nii.get_fdata().astype(np.float32)

        # =========================
        # 2. MAXIMUM ENTROPY THRESHOLD
        # =========================
        # Escludi background
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
        spacing = nii.header.get_zooms()[:3]

        kernelSizeVoxel = [
            int(round((kernelSizeMm / spacing[i] + 1) / 2) * 2 - 1)
            for i in range(3)
        ]
        kernelSizeVoxel = [k if k % 2 == 1 else k + 1 for k in kernelSizeVoxel]

        print("Kernel size voxel:", kernelSizeVoxel)

        structure = np.ones(kernelSizeVoxel, dtype=bool)

        # =========================
        # 5. CLOSING MORFOLOGICO
        # =========================
        binary_smoothed = binary_closing(binary, structure=structure)

        # riempi buchi interni
        binary_smoothed = binary_fill_holes(binary_smoothed)

        input_pd, input_spacing = self.update_input_pd_from_binary(binary_smoothed, spacing)

        regionPd = self._getInitialRegionPd(input_spacing, input_pd)

        shrunkenPd = vtk.vtkPolyData()
        shrunkenPd.DeepCopy(self._shrinkWrap(regionPd, input_spacing, input_pd))

        shrunkenPd.DeepCopy(self._extractCavity(shrunkenPd, input_spacing, input_pd))

        shrunkenPd.DeepCopy(SegmentEndocranium._smoothPolydata(shrunkenPd, 0.2))

        # =========================
        # 6. SALVA NIFTI
        # =========================
        header = shrunkenPd.header.copy()
        header.set_data_dtype(np.uint8)

        out = nib.Nifti1Image(
            binary_smoothed.astype(np.uint8),
            affine=shrunkenPd.affine,
            header=header
        )

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



