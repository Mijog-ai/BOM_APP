import pyodbc

CONN_STRING = (
    'DRIVER={SQL Server};'
    'SERVER=DEBLNSVERP01;'
    'DATABASE=XALinl;'
    'UID=XAL_ODBC;'
    'PWD=XAL_ODBC'
)


def get_connection():
    return pyodbc.connect(CONN_STRING)
