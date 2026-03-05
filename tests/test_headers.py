from src.pipeline import NOT_USED_RE, SET_HEADER_RE, normalize_mfr_finish, parse_component_line
from src.schemas.models import Component


def test_set_header_regex() -> None:
    m = SET_HEADER_RE.search("SET #3A - ENTRANCE DOORS")
    assert m
    assert m.group(1) == "3A"


def test_not_used_regex() -> None:
    assert NOT_USED_RE.search("SET #5 - NOT USED")
    assert NOT_USED_RE.search("SET 8 N/A")


def test_parse_component_line_structured() -> None:
    line = "2  HINGE, BALL BEARING  BB1279  IVE  US26D"
    c = parse_component_line(line)
    assert c is not None
    assert c.qty == "2"
    assert c.catalog_number == "BB1279"
    assert c.mfr == "IVE"
    assert c.finish == "US26D"


def test_parse_component_line_note() -> None:
    line = "LOCKSET L9050 SCH NOTE: CLASSROOM FUNCTION"
    c = parse_component_line(line)
    assert c is not None
    assert c.notes == "CLASSROOM FUNCTION"


def test_normalize_mfr_finish_swap() -> None:
    components = [Component(qty="1", description="Closer", catalog_number="4040", mfr="US26D", finish="LCN")]
    normalize_mfr_finish(components)
    assert components[0].mfr == "LCN"
    assert components[0].finish == "US26D"
