import warnings
import pytest

from pymysql.tests import base
import pymysql.cursors


class CursorTest(base.PyMySQLTestCase):
    def setUp(self):
        super(CursorTest, self).setUp()

        conn = self.connect()
        self.safe_create_table(conn, "test", "create table test (data varchar(10))")
        cursor = conn.cursor()
        with conn as cursor:
            cursor.execute(
                "insert into test (data) values "
                "('row1'), ('row2'), ('row3'), ('row4'), ('row5')"
            )
        self.test_connection = pymysql.connect(**self.databases[0])
        self.addCleanup(self.test_connection.close)

    def test_cleanup_rows_unbuffered(self):
        conn = self.test_connection
        with conn.cursor(pymysql.cursors.SSCursor) as cursor:
            cursor.execute("select * from test as t1, test as t2")
            for counter, row in enumerate(cursor):
                if counter > 10:
                    break

        self.safe_gc_collect()

        with conn as c2:
            c2.execute("select 1")
            self.assertEqual(c2.fetchone(), (1,))
            self.assertIsNone(c2.fetchone())

    def test_cleanup_rows_buffered(self):
        conn = self.test_connection
        with conn.cursor(pymysql.cursors.Cursor) as cursor:
            cursor.execute("select * from test as t1, test as t2")
            for counter, row in enumerate(cursor):
                if counter > 10:
                    break

        self.safe_gc_collect()

        with conn as c2:
            c2.execute("select 1")

            self.assertEqual(c2.fetchone(), (1,))
            self.assertIsNone(c2.fetchone())

    def test_executemany(self):
        conn = self.test_connection
        with conn.cursor(pymysql.cursors.Cursor) as cursor:
            m = pymysql.cursors.RE_INSERT_VALUES.match(
                "INSERT INTO TEST (ID, NAME) VALUES (%s, %s)"
            )
            self.assertIsNotNone(m, "error parse %s")
            self.assertEqual(
                m.group(3), "", "group 3 not blank, bug in RE_INSERT_VALUES?"
            )

            m = pymysql.cursors.RE_INSERT_VALUES.match(
                "INSERT INTO TEST (ID, NAME) VALUES (%(id)s, %(name)s)"
            )
            self.assertIsNotNone(m, "error parse %(name)s")
            self.assertEqual(
                m.group(3), "", "group 3 not blank, bug in RE_INSERT_VALUES?"
            )

            m = pymysql.cursors.RE_INSERT_VALUES.match(
                "INSERT INTO TEST (ID, NAME) VALUES (%(id_name)s, %(name)s)"
            )
            self.assertIsNotNone(m, "error parse %(id_name)s")
            self.assertEqual(
                m.group(3), "", "group 3 not blank, bug in RE_INSERT_VALUES?"
            )

            m = pymysql.cursors.RE_INSERT_VALUES.match(
                "INSERT INTO TEST (ID, NAME) VALUES (%(id_name)s, %(name)s) ON duplicate update"
            )
            self.assertIsNotNone(m, "error parse %(id_name)s")
            self.assertEqual(
                m.group(3),
                " ON duplicate update",
                "group 3 not ON duplicate update, bug in RE_INSERT_VALUES?",
            )

            # https://github.com/PyMySQL/PyMySQL/pull/597
            m = pymysql.cursors.RE_INSERT_VALUES.match(
                "INSERT INTO bloup(foo, bar)VALUES(%s, %s)"
            )
            assert m is not None

            # cursor._executed must bee "insert into test (data) values (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)"
            # list args
            data = range(10)
            cursor.executemany("insert into test (data) values (%s)", data)
            self.assertTrue(
                cursor._executed.endswith(b",(7),(8),(9)"),
                "execute many with %s not in one query",
            )

            # dict args
            data_dict = [{"data": i} for i in range(10)]
            cursor.executemany("insert into test (data) values (%(data)s)", data_dict)
            self.assertTrue(
                cursor._executed.endswith(b",(7),(8),(9)"),
                "execute many with %(data)s not in one query",
            )

            # %% in column set
            cursor.execute(
                """\
                CREATE TABLE percent_test (
                    `A%` INTEGER,
                    `B%` INTEGER)"""
            )
            try:
                q = "INSERT INTO percent_test (`A%%`, `B%%`) VALUES (%s, %s)"
                self.assertIsNotNone(pymysql.cursors.RE_INSERT_VALUES.match(q))
                cursor.executemany(q, [(3, 4), (5, 6)])
                self.assertTrue(
                    cursor._executed.endswith(b"(3, 4),(5, 6)"),
                    "executemany with %% not in one query",
                )
            finally:
                cursor.execute("DROP TABLE IF EXISTS percent_test")

    def test_happy_execute_one_column(self):
        conn = self.connect()
        self.safe_create_table(conn, "mine", "create table mine (column1 int)")
        with conn as cursor:
            cursor.execute("insert into mine (column1) values (%s)", (1,))
        with conn as c2:
            c2.execute("select * from mine")
            self.assertEqual(c2.fetchone(), (1,))
            self.assertIsNone(c2.fetchone())

    def test_happy_path_executed_two_column(self):
        conn = self.connect()
        self.safe_create_table(
            conn, "mine2", "create table mine2 (column1 int, column2 int)"
        )

        with conn as cursor:
            cursor.execute(
                "insert into mine2 (column1, column2) values (%s,%s)", (1, 2)
            )

        with conn as c2:
            c2.execute("select * from mine2")
            self.assertEqual(c2.fetchone(), (1, 2))
            self.assertIsNone(c2.fetchone())

    def happy_path_executed_three_column(self):
        conn = self.connect()
        self.safe_create_table(
            conn, "mine3", "create table mine3 (column1 int, column2 int, column3 int)"
        )

        with conn as cursor:
            cursor.execute(
                "insert into mine3 (column1, column2, column3) values (%s,%s,%s)",
                (1, 2, 3),
            )

        with conn as c3:
            c3.execute("select * from mine3")
            self.assertEqual(c3.fetchone(), (1, 2, 3))
            self.assertIsNone(c3.fetchone())

    def test_cursor_closed(self):
        conn = self.connect()
        cursor = conn.connect()
        conn.close()
        assert cursor is None


class PreparedCursorTest(base.PyMySQLTestCase):
    def test_happy_PreparedCursor(self):
        # happy path
        conn = self.connect()
        old_cursorclass = conn.cursorclass
        conn.cursorclass = pymysql.PreparedCursor
        self.safe_create_table(conn, "test", "create table test (column1 varchar(10))")

        prepared_cursor = conn.cursor()

        stmt = "insert into test (column1) VALUES (%s)"
        prepared_cursor.prepared_statement(stmt)
        assert prepared_cursor.stmt == stmt

        for i in range(5):
            prepared_cursor.add_parameters([str(i)])
            assert prepared_cursor.params == [str(i)]
            prepared_cursor.prepared_execute()
            conn.commit()
            prepared_cursor.reset_parameters()
            assert prepared_cursor.params == []

        stmt = "select test.column1 from test"
        prepared_cursor.prepared_statement(stmt)
        prepared_cursor.reset_parameters()
        prepared_cursor.prepared_execute()
        results = prepared_cursor.fetchall()

        z = 0
        for row in results:
            assert row[0] == str(z)
            z = z + 1

        conn.cursorclass = old_cursorclass

    def test_bad_statement(self):
        # bad_path
        conn = self.connect()
        old_cursorclass = conn.cursorclass
        conn.cursorclass = pymysql.PreparedCursor
        self.safe_create_table(
            conn, "test2", "create table test2 (column1 varchar(10))"
        )

        prepared_cursor = conn.cursor()

        stmt = 1
        prepared_cursor.prepared_statement(stmt)
        prepared_cursor.add_parameters(["0"])
        assert TypeError

        conn.cursorclass = old_cursorclass

    def test_bad_parameters(self):
        conn = self.connect()

        old_cursorclass = conn.cursorclass
        conn.cursorclass = pymysql.PreparedCursor
        self.safe_create_table(
            conn, "test3", "create table test3 (column1 varchar(10))"
        )

        stmt = "insert into test3 (column1) VALUES (%s)"
        prepared_cursor = conn.cursor()
        prepared_cursor.prepared_statement(stmt)

        with pytest.raises(TypeError):
            prepared_cursor.add_parameters("0", "1", "2")
            assert TypeError

        conn.cursorclass = old_cursorclass

    def test_bad_path_reset_params(self):
        conn = self.connect()

        old_cursorclass = conn.cursorclass
        conn.cursorclass = pymysql.PreparedCursor
        prepared_cursor = conn.cursor()

        with pytest.raises(TypeError):
            prepared_cursor.reset_parameters("0", "1", "2")
            assert TypeError

        conn.cursorclass = old_cursorclass

    def test_bad_path_execute(self):
        conn = self.connect()

        old_cursorclass = conn.cursorclass
        conn.cursorclass = pymysql.PreparedCursor
        self.safe_create_table(
            conn, "test4", "create table test4 (column1 varchar(10))"
        )

        prepared_cursor = conn.cursor()

        stmt = "insert into test4 (column1) VALUES (%s)"
        prepared_cursor.prepared_statement(stmt)
        prepared_cursor.add_parameters(["0"])

        with pytest.raises(TypeError):
            prepared_cursor.prepared_execute("here")
            assert TypeError

        conn.cursorclass = old_cursorclass
