import json
from pathlib import Path
from django.db import migrations


def import_content(apps, schema_editor):
    rows = json.loads(Path(__file__).with_name("initial_content.json").read_text())
    for row in rows:
        apps.get_model("portfolio", row["model"]).objects.using(schema_editor.connection.alias).create(**row["fields"])


class Migration(migrations.Migration):
    dependencies = [("portfolio", "0001_initial")]
    # Applied once; future deployments never overwrite edits or restore deletions.
    operations = [migrations.RunPython(import_content, migrations.RunPython.noop)]
