from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0030_alter_subject_academic_year'),
    ]

    operations = [
        migrations.AddField(
            model_name='subject',
            name='semester',
            field=models.CharField(
                max_length=20,
                choices=[('1st Semester', '1st Semester'), ('2nd Semester', '2nd Semester'), ('Summer', 'Summer')],
                default='1st Semester',
                help_text='Semester this subject is offered',
            ),
        ),
    ]
