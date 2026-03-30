from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_documenttype_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="dossier",
            name="is_non_syrian",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="dossier",
            name="nationality_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
