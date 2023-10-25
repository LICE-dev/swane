import shutil
import sys
from PySide6.QtWidgets import QMessageBox
from pyshortcuts.linux import get_desktop, get_startmenu, get_homedir
from swane import strings
import swane_supplement
import os
import subprocess
import __main__
import time

main_module_name = os.path.basename(os.path.dirname(__main__.__file__))

mac_package_name = strings.APPNAME + ".app"
mac_shell_command = "dscl . -read ~/ UserShell | sed 's/UserShell: //'"
mac_exec_file_content = sys.executable + " -m " + main_module_name
mac_info_file_name = "Info.plist"
mac_info_file_content = """<?xml version="1.0" encoding="UTF-8"?>
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

linux_file_name = strings.APPNAME + ".desktop"
linux_file_content = """[Desktop Entry]
Name=""" + strings.APPNAME + """
Type=Application
Path=""" + get_homedir() + """
Comment=""" + strings.APPNAME + """
Terminal=false
Icon=""" + swane_supplement.appIcon_file + """
Exec=""" + os.environ.get("SHELL", "bash") + " -l -i -c '" + sys.executable + " -m " + main_module_name + "'"


def shortcut_manager(global_config):
    if global_config.get_shortcut_path() == "":

        if sys.platform == "darwin":
            mac_user_application_path = os.path.join(get_homedir(), "Applications")
            os.makedirs(mac_user_application_path, exist_ok=True)
            mac_package_path = os.path.join(mac_user_application_path, mac_package_name)

            shutil.rmtree(mac_package_path, ignore_errors=True)
            os.makedirs(mac_package_path, exist_ok=True)

            os.makedirs(os.path.join(mac_package_path, 'Contents'), exist_ok=True)
            info_file = os.path.join(mac_package_path, 'Contents', mac_info_file_name)
            with open(info_file, 'w') as f:
                f.write(mac_info_file_content)

            os.makedirs(os.path.join(mac_package_path, 'Contents', 'MacOS'), exist_ok=True)
            exec_file = os.path.join(mac_package_path, 'Contents', 'MacOS', strings.APPNAME)
            user_shell = subprocess.run(mac_shell_command, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8').replace("\n", "")
            this_content = "#!" + user_shell + " -i -l \n" + mac_exec_file_content
            with open(exec_file, 'w') as f:
                f.write(this_content)
            os.chmod(exec_file, 493)

            os.makedirs(os.path.join(mac_package_path, 'Contents', 'Resources'), exist_ok=True)
            icns_file = os.path.join(mac_package_path, 'Contents', 'Resources', os.path.basename(swane_supplement.appIcns_file))
            shutil.copyfile(swane_supplement.appIcns_file, icns_file)

            mac_desktop_link = os.path.join(get_desktop(), strings.APPNAME)
            if os.path.exists(mac_desktop_link):
                os.remove(mac_desktop_link)
            os.symlink(mac_package_path, mac_desktop_link)

            targets = [mac_package_path, mac_desktop_link]
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
            if strings.APPNAME in fil and (os.path.exists(fil) or os.path.islink(fil)):
                if os.path.isdir(fil):
                    shutil.rmtree(fil, ignore_errors=True)
                else:
                    os.remove(fil)
        global_config.set_shortcut_path("")
        msg_box = QMessageBox()
        msg_box.setText(strings.mainwindow_shortcut_removed)
        msg_box.exec()
    global_config.save()
