"""Compatibility fix for Open3D 0.13 with Ubuntu 18.04 OpenBLAS headers."""
from pathlib import Path
import re

root = Path(__file__).resolve().parent
header = root / 'vendor/Open3D/cpp/open3d/core/linalg/BlasWrapper.h'
original = header.read_text()
# Infer the CBLAS enum type from its value, valid for both ORDER and LAYOUT APIs.
old = 'CBLAS_LAYOUT layout'
new = 'decltype(CblasRowMajor) layout'
if old in original:
    assert original.count(old) == 3, 'Unexpected Open3D source; refusing broad edit'
    backup = header.with_suffix('.h.before-jetscan-blas-fix')
    if not backup.exists():
        backup.write_text(original)
    header.write_text(original.replace(old, new))
    print('Patched three BLAS wrapper declarations; original header backed up.')
else:
    assert original.count(new) == 3, 'Unexpected Open3D source; inspect manually'
    print('BLAS compatibility patch already applied.')
