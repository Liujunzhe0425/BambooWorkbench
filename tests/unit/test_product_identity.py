from app import PRODUCT_NAME_EN, PRODUCT_NAME_ZH, __version__


def test_product_identity_is_canonical() -> None:
    assert PRODUCT_NAME_EN == "BambooWorkbench"
    assert PRODUCT_NAME_ZH == "竹简工作台"
    assert __version__ == "1.0.0"
