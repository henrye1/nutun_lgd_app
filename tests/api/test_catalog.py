from datetime import datetime

from api.catalog import REQUIRED_OBJECTS, ObjectInfo, check_objects


class FakeCatalog:
    def __init__(self, objects: dict[str, ObjectInfo], counts: dict[str, int]):
        self.objects, self.counts = objects, counts

    def object_info(self, name):
        return self.objects.get(name)

    def row_count(self, name, kind):
        return self.counts.get(name)


def _full():
    objs = {o.name: ObjectInfo(o.name, o.kind, datetime(2026, 8, 1), list(o.columns)) for o in REQUIRED_OBJECTS}
    return objs, {o.name: 10 for o in REQUIRED_OBJECTS}


def test_required_objects_cover_spec_4_1():
    names = {o.name for o in REQUIRED_OBJECTS}
    assert {
        "ACM_Payments", "ACM_Payments_VB44_Excluded", "ACM_Master", "ACM_Snap_BookUniverse", "ACM_VB",
        "ACM_VB_Alloc", "ACM_CAEIR", "ACM_FLI", "ACM_Costs", "ACM_Costs_Cohorts", "ACM_Capping", "ACM_Config",
        "fn_APP_Info",
    } <= names
    fn = next(o for o in REQUIRED_OBJECTS if o.name == "fn_APP_Info")
    assert fn.kind == "function" and fn.sql_file == "sql/fn_APP_Info.sql"


def test_all_present_is_ok():
    objs, counts = _full()
    st = check_objects(FakeCatalog(objs, counts))
    assert all(s.ok and s.exists and s.row_count == 10 and s.missing_columns == [] for s in st)


def test_missing_function_and_missing_column_are_reported():
    objs, counts = _full()
    del objs["fn_APP_Info"]
    objs["ACM_FLI"] = ObjectInfo("ACM_FLI", "table", None, ["Date", "R2"])  # Adj missing
    st = {s.name: s for s in check_objects(FakeCatalog(objs, counts))}
    assert not st["fn_APP_Info"].exists and not st["fn_APP_Info"].ok
    assert "sql/fn_APP_Info.sql" in st["fn_APP_Info"].hint
    assert st["ACM_FLI"].exists and st["ACM_FLI"].missing_columns == ["Adj"] and not st["ACM_FLI"].ok
