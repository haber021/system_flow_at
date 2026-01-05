# Generated manually
from django.db import migrations

def migrate_student_sections(apps, schema_editor):
    """Migrate student sections from char codes to Section objects"""
    Section = apps.get_model('attendance', 'Section')
    Student = apps.get_model('attendance', 'Student')
    
    # Get all sections
    section_map = {sec.code: sec for sec in Section.objects.all()}
    
    # Get default section (Section A)
    default_section = section_map.get('A')
    
    # Update students that don't have a section assigned
    if default_section:
        Student.objects.filter(section__isnull=True).update(section=default_section)

def reverse_migration(apps, schema_editor):
    """Reverse migration - no action needed"""
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0015_add_section_model'),
    ]

    operations = [
        migrations.RunPython(migrate_student_sections, reverse_migration),
    ]

