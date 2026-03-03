import pyodbc


def ConnStringXAL():
    return (f'DRIVER={{SQL Server}};SERVER=DEBLNSVERP01;DATABASE=XALinl;UID=XAL_ODBC;PWD=XAL_ODBC')


def findInfo5(itemNo):
    try:
        # Establish connection
        conn = pyodbc.connect(ConnStringXAL())

        query = """
                SELECT B407SBM_INL.SCRIPTNUM AS 'Pos.', STOCKBILLMAT.CHILDITEMNO AS 'Num. / No.', STOCKTABLE.ITEMNAME AS 'Bezeichnung', TEXTS.TXT1 AS 'Name', STOCKBILLMAT.QTYTURNOVR AS 'Qty', STOCKBILLMAT.POSITION, \
                       STOCKTABLE_1.ITEMNUMBER, \
                       STOCKTABLE_1.ITEMNAME, \
                       TEXTS_1.TXT1
                FROM XALinl.dbo.B407SBM_INL B407SBM_INL, \
                     XALinl.dbo.STOCKBILLMAT STOCKBILLMAT, \
                     XALinl.dbo.STOCKTABLE STOCKTABLE, \
                     XALinl.dbo.STOCKTABLE STOCKTABLE_1, \
                     XALinl.dbo.TEXTS TEXTS, \
                     XALinl.dbo.TEXTS TEXTS_1
                WHERE B407SBM_INL.DATASET = STOCKBILLMAT.DATASET
                  AND STOCKBILLMAT.LINENO_ = B407SBM_INL.LINENO_
                  AND STOCKBILLMAT.FATHERITEMNO = B407SBM_INL.FATHERITEMNUM
                  AND STOCKTABLE.DATASET = STOCKBILLMAT.DATASET
                  AND STOCKBILLMAT.CHILDITEMNO = STOCKTABLE.ITEMNUMBER
                  AND TEXTS.DATASET = STOCKTABLE.DATASET
                  AND STOCKTABLE.ITEMNUMBER = TEXTS.TXTID
                  AND TEXTS.DATASET = STOCKTABLE_1.DATASET
                  AND STOCKBILLMAT.FATHERITEMNO = STOCKTABLE_1.ITEMNUMBER
                  AND TEXTS_1.DATASET = TEXTS.DATASET
                  AND STOCKTABLE_1.ITEMNUMBER = TEXTS_1.TXTID
                  AND ((STOCKBILLMAT.DATASET = 'INL') AND (STOCKBILLMAT.FATHERITEMNO LIKE ?))
                ORDER BY STOCKBILLMAT.POSITION \
                """

        cursor = conn.cursor()
        cursor.execute(query, (itemNo,))

        # Fetch column names
        columns = [column[0] for column in cursor.description]

        # Fetch all records
        rows = cursor.fetchall()

        # Convert to list of dicts for easier use
        results = [dict(zip(columns, row)) for row in rows]

        conn.close()

        # Print results nicely
        for row in results:
            print(row)

        return results

    except pyodbc.Error as e:
        print(f"Database error: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


# --- Usage ---
if __name__ == "__main__":
    # Exact match
    item_number = "YOUR_ITEM_NUMBER"
    results = findInfo5(item_number)

    # Wildcard search (LIKE pattern)
    # results = findInfo5("ITEM123%")   # starts with
    # results = findInfo5("%ITEM123%")  # contains

    print(f"\nTotal records found: {len(results)}")