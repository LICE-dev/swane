import shutil
import sys
from PySide6.QtWidgets import QMessageBox
from pyshortcuts.linux import get_desktop, get_startmenu, get_homedir
from swane import strings
import swane_supplement
import os

os_package_name = strings.APPNAME + ".app"
os_info_file_name = "Info.plist"
os_info_file_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
  <key>CFBundleGetInfoString</key> <string>""" + strings.APPNAME + """</string>
  <key>CFBundleName</key> <string>""" + strings.APPNAME + """</string>
  <key>CFBundleExecutable</key> <string>""" + strings.APPNAME + """</string>
  <key>CFBundleIconFile</key> <string>""" + os.path.basename(swane_supplement.appIcns_file) + """</string>
  <key>CFBundlePackageType</key> <string>APPL</string>
  </dict>
</plist>"""

os_exec_file_content = "#!" + os.environ.get("SHELL", "/bin/bash") + """
osascript -e 'tell application "Terminal"
   do script "
export PYTHON_EXE=""" + sys.executable + """;
   $PYTHON_EXE -m """ + strings.APPNAME.lower() + """
   "
end tell
'"""

linux_file_name = strings.APPNAME + ".desktop"

linux_file_content = """[Desktop Entry]
Name=""" + strings.APPNAME + """
Type=Application
Path=""" + get_homedir() + """
Comment=""" + strings.APPNAME + """
Terminal=false
Icon=""" + swane_supplement.appIcon_file + """
Exec=""" + os.environ.get("SHELL", "bash") + " -i -c '" + sys.executable + " -m " + strings.APPNAME.lower() + "'"


def shortcut_manager(global_config):
    if global_config.get_shortcut_path() == "":

        if sys.platform == "darwin":
            package_path = os.path.join(get_desktop(), os_package_name)
            targets = [package_path]
            shutil.rmtree(package_path, ignore_errors=True)
            os.makedirs(package_path, exist_ok=True)

            os.makedirs(os.path.join(package_path, 'Contents'), exist_ok=True)
            info_file = os.path.join(package_path, 'Contents', os_info_file_name)
            with open(info_file, 'w') as f:
                f.write(os_info_file_content)

            os.makedirs(os.path.join(package_path, 'Contents', 'MacOS'), exist_ok=True)
            exec_file = os.path.join(package_path, 'Contents', 'MacOS', strings.APPNAME)
            with open(exec_file, 'w') as f:
                f.write(os_exec_file_content)
            os.chmod(exec_file, 493)

            os.makedirs(os.path.join(package_path, 'Contents', 'Resources'), exist_ok=True)
            icns_file = os.path.join(package_path, 'Contents', 'Resources', os.path.basename(swane_supplement.appIcns_file))
            shutil.copyfile(swane_supplement.appIcns_file, icns_file)

        else:
            targets = [os.path.join(get_desktop(), linux_file_name), os.path.join(get_startmenu(), linux_file_name)]
            for file in targets:
                with open(file, 'w') as f:
                    f.write(linux_file_content)
                os.chmod(file, 493)

        global_config.set_shortcut_path("|".join(targets))
        msg_box = QMessageBox()
        msg_box.setText(strings.mainwindow_shortcut_created)
        msg_box.exec()
    else:
        targets = global_config.get_shortcut_path().split("|")
        for fil in targets:
            if strings.APPNAME in fil and os.path.exists(fil):
                if os.path.isdir(fil):
                    shutil.rmtree(fil, ignore_errors=True)
                else:
                    os.remove(fil)
        global_config.set_shortcut_path("")
        msg_box = QMessageBox()
        msg_box.setText(strings.mainwindow_shortcut_removed)
        msg_box.exec()
    global_config.save()
