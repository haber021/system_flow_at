from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0027_absent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendance',
            name='calendar_event',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='applied_attendances', to='attendance.calendarevent'),
        ),
    ]
