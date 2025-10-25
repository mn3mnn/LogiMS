from django.db import migrations
from django.core.management import call_command


def add_uber_eats_tax_config(apps, schema_editor):
    """Add tax configuration for Uber Eats with 19% tax rate"""
    Company = apps.get_model('companies', 'Company')
    TaxConfiguration = apps.get_model('data_imports', 'TaxConfiguration')

    # Find Uber Eats company
    try:
        uber_eats_company = Company.objects.get(code__iexact='uber_eats', is_active=True)

        # Create tax configuration if it doesn't exist
        tax_config, created = TaxConfiguration.objects.get_or_create(
            company=uber_eats_company,
            name='Income Tax',
            defaults={
                'tax_rate': 19.0,
                'is_active': True,
                'description': 'Income tax rate for Uber Eats drivers'
            }
        )

        if created:
            print(f'✅ Created tax configuration for {uber_eats_company.name}: 19.0%')
        else:
            print(f'ℹ️  Tax configuration already exists for {uber_eats_company.name}')

    except Company.DoesNotExist:
        print('⚠️  Uber Eats company not found. Please create a company with code "uber_eats" first.')


def remove_uber_eats_tax_config(apps, schema_editor):
    """Remove Uber Eats tax configuration"""
    Company = apps.get_model('companies', 'Company')
    TaxConfiguration = apps.get_model('data_imports', 'TaxConfiguration')

    try:
        uber_eats_company = Company.objects.get(code__iexact='uber_eats')
        TaxConfiguration.objects.filter(
            company=uber_eats_company,
            name='Income Tax'
        ).delete()
        print(f'✅ Removed tax configuration for {uber_eats_company.name}')
    except Company.DoesNotExist:
        print('⚠️  Uber Eats company not found.')


class Migration(migrations.Migration):

    dependencies = [
        ('data_imports', '0001_initial'),
        ('companies', '0002_add_uber_eats'),
    ]

    operations = [
        migrations.RunPython(
            add_uber_eats_tax_config,
            remove_uber_eats_tax_config,
        ),
    ]
