import pyodbc


def get_connection():
    conn_string = (
        'DRIVER={SQL Server};'
        'SERVER=DEBLNSVERP01;'
        'DATABASE=XALinl;'
        'UID=XAL_ODBC;'
        'PWD=XAL_ODBC'
    )
    return pyodbc.connect(conn_string)
