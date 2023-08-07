import sys
import os
from datetime import datetime
from swane import strings
from inspect import getframeinfo, stack

ERROR_FILE = os.path.abspath(os.path.join(os.path.expanduser("~"), "." + strings.APPNAME) + "_errorlog")


def print_error():
    """
    Print a standardized Error Log string

    Parameters
    ----------
    e : Exception
        The Exception TypeError.

    Returns
    -------
    string
        The formatted error string.

    """

    try:
        exception_type = repr(sys.exc_info()[1])
        caller = getframeinfo(stack()[1][0])
        function_name = caller.function
        file_name = caller.filename
        line_number = caller.lineno
        message = f"\n\n{datetime.now().strftime('%Y/%m/%d, %H:%M:%S')} - File name: {file_name} - Func name: {function_name} - Exception type: {exception_type} at Line: {line_number}"


        with open(ERROR_FILE, 'a+') as f:
            f.write(message)

    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print(f"{datetime.now().strftime('%Y/%m/%d, %H:%M:%S')} - " +
              f"File name: {os.path.normpath(os.path.basename(exception_traceback.tb_frame.f_code.co_filename))} - Func name: print_error - " +
              f"Exception type: {exception_type} " +
              f"at Line: {line_number} - " +
              f"{str(e)}")
