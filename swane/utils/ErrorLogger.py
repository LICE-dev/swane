import sys
import os
from datetime import datetime


def print_error(exc_info, function_name, e):
    """
    Print a standardized Error Log string

    Parameters
    ----------
    exc_info : sys.exc_info()
        The Exception system info.
    function_name : string
        The Exception function name.
    e : TypeError
        The Exception TypeError.

    Returns
    -------
    string
        The formatted error string.

    """

    try:
        exception_type = exc_info[0]
        exception_object = exc_info[1]
        exception_traceback = exc_info[2]
        file_name = os.path.normpath(os.path.basename(exception_traceback.tb_frame.f_code.co_filename))
        line_number = exception_traceback.tb_lineno

        message = f"{datetime.now().strftime('%Y/%m/%d, %H:%M:%S')} - File name: {file_name} - Func name: {function_name} - Exception type: {exception_type} at Line: {line_number} - {str(e)}"

        return message

    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        file_name = exception_traceback.tb_frame.f_code.co_filename
        line_number = exception_traceback.tb_lineno
        print(f"{datetime.now().strftime('%Y/%m/%d, %H:%M:%S')} - " +
              f"File name: {os.path.normpath(os.path.basename(exception_traceback.tb_frame.f_code.co_filename))} - Func name: print_error - " +
              f"Exception type: {exception_type} " +
              f"at Line: {line_number} - " +
              f"{str(e)}")


def datetime_handler(x):
    if isinstance(x, datetime):
        return x.isoformat()