# GridQuant R1 local input bundle

This directory contains frozen inputs, not an installed application.
Keep its relative paths intact; it can be moved independently of the repository.

From the project, after installing dependencies:

```sh
uv run python final_evaluation.py --input-dir demo_inputs --output outputs/demo --offline
```

The wrapper loads this bundle; it never downloads missing data. Output must be new.
The bundle manifest hashes every included file except itself. Hashes detect changes
relative to this inventory; they are not a digital signature or proof of source accuracy.

See ATTRIBUTION.md for the saved data license and transformations. The config and
validation reports freeze alpha 100 and the previous-day reference. The expected
metrics are the already-inspected final result and are provided for reproduction,
not further model selection. Actual historical availability remains unverified.

The included lockfile and project metadata describe dependencies; they do not bundle
Python or dependency wheels. A fresh installation may require network access.
