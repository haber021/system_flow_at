# Generated manually: Add FeatureSuggestion model
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0034_remove_attendance_evidence_absenceevidence'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureSuggestion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('status', models.CharField(choices=[('NEW', 'New'), ('REVIEWED', 'Reviewed'), ('IMPLEMENTED', 'Implemented'), ('REJECTED', 'Rejected')], default='NEW', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feature_suggestions', to='attendance.student')),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Feature Suggestion',
                'verbose_name_plural': 'Feature Suggestions',
            },
        ),
    ]
