from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(model_name="user", name="mfa_secret"),
        migrations.RemoveField(model_name="user", name="mfa_enabled"),
        migrations.RemoveField(model_name="user", name="mfa_confirmed"),
        migrations.RemoveField(model_name="user", name="recovery_codes"),
        migrations.DeleteModel(name="TrustedDevice"),
    ]
