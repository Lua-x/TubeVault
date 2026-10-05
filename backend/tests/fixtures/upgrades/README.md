# Upgrade fixtures

One set per release, made by **that release's own code**: `build_fixture.py` is copied into a
checkout of the release and run with its own test fakes, so everything goes through the old
API exactly as it did back then.

| File | Contents |
| ---- | -------- |
| `vX.Y.Z.db.gz` | The database after adding three videos, a second user, changed settings, watch progress, a playlist, watch later, a subscription, an API token and a family device – whatever the release knew |
| `vX.Y.Z.json` | What a newer TubeVault must still show (only test credentials) |
| `vX.Y.Z.zip` | A backup made by that release (from 0.5 on) |

`tests/test_updates.py` starts the current version on every database and restores every
backup, then checks the values and that new videos can still be added.

## Adding the next release

After tagging a release, build its fixture so later versions are tested against it:

```sh
git worktree add /tmp/tv-old vX.Y.Z
cp backend/tests/fixtures/upgrades/build_fixture.py /tmp/tv-old/backend/tests/test_zz_build_fixture.py
cd /tmp/tv-old/backend && uv sync
FIXTURE_OUT=/tmp/vX.Y.Z uv run pytest tests/test_zz_build_fixture.py -q
gzip -9 /tmp/vX.Y.Z.db
cp /tmp/vX.Y.Z.db.gz /tmp/vX.Y.Z.json /tmp/vX.Y.Z.zip <repo>/backend/tests/fixtures/upgrades/
```
