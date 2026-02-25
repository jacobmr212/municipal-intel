"""
Salesforce CRM Integration

Uses simple-salesforce library for Salesforce REST API access.

Configuration:
{
    'username': 'user@company.com',
    'password': 'password',
    'security_token': 'token',
    'domain': 'login' or 'test' (optional, default: 'login')
}

Installation: pip install simple-salesforce
"""

from typing import Dict, Any, Optional
import logging

from .base import CRMProvider, CRMSyncResult

logger = logging.getLogger(__name__)


class SalesforceProvider(CRMProvider):
    """Salesforce CRM integration."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.sf = None

    def authenticate(self) -> bool:
        """Authenticate with Salesforce using username/password/token."""
        try:
            from simple_salesforce import Salesforce

            self.sf = Salesforce(
                username=self.config['username'],
                password=self.config['password'],
                security_token=self.config['security_token'],
                domain=self.config.get('domain', 'login')
            )

            self._authenticated = True
            logger.info(f"✓ Authenticated with Salesforce as {self.config['username']}")
            return True

        except ImportError:
            logger.error("simple-salesforce library not installed. Install with: pip install simple-salesforce")
            return False

        except Exception as e:
            logger.error(f"Salesforce authentication failed: {e}")
            return False

    def create_lead(self, lead_data: Dict[str, Any]) -> CRMSyncResult:
        """Create a new lead in Salesforce."""
        try:
            # Map fields to Salesforce schema
            sf_data = self._map_to_salesforce(lead_data)

            # Create lead
            result = self.sf.Lead.create(sf_data)

            if result.get('success'):
                lead_id = result['id']
                lead_url = f"{self.sf.sf_instance}/{lead_id}"

                logger.info(f"✓ Created Salesforce lead: {lead_id}")

                return CRMSyncResult(
                    success=True,
                    crm_lead_id=lead_id,
                    crm_url=lead_url
                )
            else:
                errors = result.get('errors', [])
                error_msg = ', '.join([e.get('message', str(e)) for e in errors])

                logger.error(f"Failed to create Salesforce lead: {error_msg}")

                return CRMSyncResult(
                    success=False,
                    error_message=error_msg
                )

        except Exception as e:
            logger.error(f"Exception creating Salesforce lead: {e}")
            return CRMSyncResult(
                success=False,
                error_message=str(e)
            )

    def update_lead(self, crm_lead_id: str, lead_data: Dict[str, Any]) -> CRMSyncResult:
        """Update an existing lead in Salesforce."""
        try:
            sf_data = self._map_to_salesforce(lead_data)

            # Update lead
            result = self.sf.Lead.update(crm_lead_id, sf_data)

            lead_url = f"{self.sf.sf_instance}/{crm_lead_id}"

            logger.info(f"✓ Updated Salesforce lead: {crm_lead_id}")

            return CRMSyncResult(
                success=True,
                crm_lead_id=crm_lead_id,
                crm_url=lead_url
            )

        except Exception as e:
            logger.error(f"Exception updating Salesforce lead {crm_lead_id}: {e}")
            return CRMSyncResult(
                success=False,
                crm_lead_id=crm_lead_id,
                error_message=str(e)
            )

    def get_lead(self, crm_lead_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a lead from Salesforce by ID."""
        try:
            lead = self.sf.Lead.get(crm_lead_id)
            return lead

        except Exception as e:
            logger.error(f"Failed to get Salesforce lead {crm_lead_id}: {e}")
            return None

    def search_lead(self, email: Optional[str] = None,
                   company: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search for a lead in Salesforce by email or company."""
        try:
            # Build SOQL query
            conditions = []

            if email:
                conditions.append(f"Email = '{email}'")

            if company:
                # Escape single quotes in company name
                safe_company = company.replace("'", "\\'")
                conditions.append(f"Company = '{safe_company}'")

            if not conditions:
                return None

            query = f"SELECT Id, Company, Email, Status FROM Lead WHERE {' OR '.join(conditions)} LIMIT 1"

            results = self.sf.query(query)

            if results['totalSize'] > 0:
                lead = results['records'][0]
                return {
                    'id': lead['Id'],
                    'company': lead.get('Company'),
                    'email': lead.get('Email'),
                    'status': lead.get('Status'),
                    'url': f"{self.sf.sf_instance}/{lead['Id']}"
                }

            return None

        except Exception as e:
            logger.error(f"Failed to search Salesforce leads: {e}")
            return None

    def _map_to_salesforce(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map generic lead data to Salesforce schema.

        Salesforce required fields:
        - Company (required)
        - LastName (required for Lead object)

        We use municipality name as both Company and LastName.
        """
        sf_data = {
            'Company': lead_data.get('Company', 'Unknown'),
            'LastName': lead_data.get('Company', 'Unknown').split(',')[0],  # Use municipality name
            'LeadSource': lead_data.get('LeadSource', 'Municipal Intel'),
            'Description': lead_data.get('Description'),
            'Status': lead_data.get('Status', 'New'),
            'Rating': lead_data.get('Rating', 'Cold'),
            'Website': lead_data.get('Website'),
            'State': lead_data.get('State'),
        }

        # Add custom fields if they exist in Salesforce
        # Note: Custom field API names end with __c
        custom_fields = {
            'Population__c': lead_data.get('Custom_Population__c'),
            'Relevance_Score__c': lead_data.get('Custom_Relevance_Score__c'),
            'Lead_Type__c': lead_data.get('Custom_Lead_Type__c'),
            'Urgency_Score__c': lead_data.get('Custom_Urgency_Score__c'),
            'Deadline__c': lead_data.get('Custom_Deadline__c'),
            'Existing_Vendor__c': lead_data.get('Custom_Existing_Vendor__c'),
            'Competitors__c': lead_data.get('Custom_Competitors__c'),
        }

        # Only include non-None custom fields
        for field, value in custom_fields.items():
            if value is not None:
                sf_data[field] = value

        return sf_data
