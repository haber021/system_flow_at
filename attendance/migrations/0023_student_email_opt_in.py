from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0022_prevent_all_duplicate_attendance'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='email_opt_in',
            field=models.BooleanField(
                default=True,
                help_text='Allow this student to receive email notifications',
            ),
        ),
    ]


