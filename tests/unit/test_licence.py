import pytest

from reelforge.cast.licence import licence_warning
from reelforge.models_registry import ModelEntry


def _entry(lic: str, url: str = "https://x.invalid/l") -> ModelEntry:
    return ModelEntry(key="image", id="img-1", revision="r", license=lic, license_url=url)


@pytest.mark.parametrize("lic", ["Apache-2.0", "mit"])
def test_permissive_has_no_warning(lic):
    assert licence_warning(_entry(lic)) is None


@pytest.mark.parametrize("lic", ["FLUX.1 [dev] Non-Commercial License", "CC-BY-NC-4.0"])
def test_non_commercial_warns(lic):
    assert licence_warning(_entry(lic)) == (
        f"Image model licence: {lic} - not for commercial use. See https://x.invalid/l."
    )


def test_empty_licence_warns():
    assert licence_warning(_entry("")) == (
        "Image model licence is not filled in. Check img-1 before commercial use."
    )
