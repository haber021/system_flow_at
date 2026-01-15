# Generated migration to add timeout_before_minutes to SystemSettings
from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0036_alter_featuresuggestion_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='timeout_before_minutes',
            field=models.IntegerField(default=15, validators=[django.core.validators.MinValueValidator(0)], help_text='Allow time-out this many minutes before class ends'),
        ),
    ]
