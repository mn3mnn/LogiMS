from django.core.management.base import BaseCommand
from faker import Faker
import random
import uuid
from datetime import timedelta
from django.utils import timezone

from logims.drivers.models import (
    Driver,
    DriverLicense,
    DriverNationalID,
    DriverVehicleLicense,
    DriverContract
)
from logims.companies.models import Company

fake = Faker()

class Command(BaseCommand):
    help = 'Seed the database with 100 test drivers and their documents'

    def handle(self, *args, **kwargs):
        Driver.objects.all().delete()
        DriverLicense.objects.all().delete()
        DriverNationalID.objects.all().delete()
        DriverVehicleLicense.objects.all().delete()
        DriverContract.objects.all().delete()

        companies = list(Company.objects.all())

        for i in range(100):
            # Create driver
            first_name = fake.first_name()
            last_name = fake.last_name()
            phone_number = fake.msisdn()
            driver_uuid = str(uuid.uuid4())
            driver_nid = str(uuid.uuid4())[0:15]
            company = random.choice(companies) if companies and random.random() < 0.8 else None
            
            # Generate realistic insurance and agency share values
            insurance = round(random.uniform(50.0, 500.0), 2)  # Insurance between €50-€500
            agency_share = round(random.uniform(0.05, 0.25), 3)  # Agency share between 0.05-0.25 (5%-25%)

            driver = Driver.objects.create(
                first_name=first_name,
                last_name=last_name,
                uuid=driver_uuid,
                nid=driver_nid,
                phone_number=phone_number,
                is_active=True,
                company=company,
                insurance=insurance,
                agency_share=agency_share
            )

            # Common fake document dates
            issue_date = fake.date_between(start_date='-2y', end_date='today')
            expiry_date = issue_date + timedelta(days=365)

            # Create DriverLicense
            DriverLicense.objects.create(
                driver=driver,
                file='driver_documents/fake_license.pdf',
                issue_date=issue_date,
                expiry_date=expiry_date,
                is_active=True,
                license_number=fake.unique.bothify(text='LIC-#####'),
                license_type=random.choice(['A', 'B', 'C']),
                notes='Auto-generated for testing'
            )

            # Create National ID
            DriverNationalID.objects.create(
                driver=driver,
                file='fake_national_id.pdf',
                issue_date=issue_date,
                expiry_date=expiry_date,
                is_active=True,
                notes='Auto-generated national ID'
            )

            # Create Vehicle License
            DriverVehicleLicense.objects.create(
                driver=driver,
                file='fake_vehicle_license.pdf',
                issue_date=issue_date,
                expiry_date=expiry_date,
                is_active=True,
                license_number=fake.unique.bothify(text='VH-#####'),
                license_plate=fake.license_plate(),
                license_type='Private',
                vehicle_type=random.choice(['Car', 'Motorbike', 'Van']),
                notes='Auto-generated vehicle license'
            )

            # Create 1-2 Contracts
            for _ in range(random.randint(1, 2)):
                DriverContract.objects.create(
                    driver=driver,
                    file='fake_contract.pdf',
                    issue_date=issue_date,
                    expiry_date=expiry_date,
                    is_active=True,
                    contract_number=fake.unique.bothify(text='CTR-#####'),
                    notes='Auto-generated contract'
                )

        self.stdout.write(self.style.SUCCESS('✅ Successfully seeded 100 drivers with full documents'))
