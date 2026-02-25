"""
HubSpot CRM Integration

Uses hubspot-api-client library for HubSpot API access.

Configuration:
{
    'access_token': 'your-private-app-access-token'
}

Installation: pip install hubspot-api-client
"""

from typing import Dict, Any, Optional
import logging

from .base import CRMProvider, CRMSyncResult

logger = logging.getLogger(__name__)


class HubSpotProvider(CRMProvider):
    """HubSpot CRM integration."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = None

    def authenticate(self) -> bool:
        """Authenticate with HubSpot using access token."""
        try:
            from hubspot import HubSpot

            self.client = HubSpot(access_token=self.config['access_token'])

            # Test authentication by getting account info
            try:
                self.client.crm.owners.get_all()
                self._authenticated = True
                logger.info("✓ Authenticated with HubSpot")
                return True

            except Exception as e:
                logger.error(f"HubSpot authentication test failed: {e}")
                return False

        except ImportError:
            logger.error("hubspot-api-client library not installed. Install with: pip install hubspot-api-client")
            return False

        except Exception as e:
            logger.error(f"HubSpot authentication failed: {e}")
            return False

    def create_lead(self, lead_data: Dict[str, Any]) -> CRMSyncResult:
        """
        Create a new contact in HubSpot.

        Note: HubSpot doesn't have a separate "Lead" object - we create Contacts.
        """
        try:
            from hubspot.crm.contacts import SimplePublicObjectInputForCreate

            # Map to HubSpot contact properties
            hs_data = self._map_to_hubspot(lead_data)

            # Create contact
            contact_input = SimplePublicObjectInputForCreate(properties=hs_data)
            result = self.client.crm.contacts.basic_api.create(simple_public_object_input_for_create=contact_input)

            contact_id = result.id
            # HubSpot contact URL format
            portal_id = self.config.get('portal_id', 'YOUR_PORTAL_ID')
            contact_url = f"https://app.hubspot.com/contacts/{portal_id}/contact/{contact_id}"

            logger.info(f"✓ Created HubSpot contact: {contact_id}")

            return CRMSyncResult(
                success=True,
                crm_lead_id=contact_id,
                crm_url=contact_url
            )

        except Exception as e:
            logger.error(f"Exception creating HubSpot contact: {e}")
            return CRMSyncResult(
                success=False,
                error_message=str(e)
            )

    def update_lead(self, crm_lead_id: str, lead_data: Dict[str, Any]) -> CRMSyncResult:
        """Update an existing contact in HubSpot."""
        try:
            from hubspot.crm.contacts import SimplePublicObjectInput

            hs_data = self._map_to_hubspot(lead_data)

            # Update contact
            contact_input = SimplePublicObjectInput(properties=hs_data)
            result = self.client.crm.contacts.basic_api.update(
                contact_id=crm_lead_id,
                simple_public_object_input=contact_input
            )

            portal_id = self.config.get('portal_id', 'YOUR_PORTAL_ID')
            contact_url = f"https://app.hubspot.com/contacts/{portal_id}/contact/{crm_lead_id}"

            logger.info(f"✓ Updated HubSpot contact: {crm_lead_id}")

            return CRMSyncResult(
                success=True,
                crm_lead_id=crm_lead_id,
                crm_url=contact_url
            )

        except Exception as e:
            logger.error(f"Exception updating HubSpot contact {crm_lead_id}: {e}")
            return CRMSyncResult(
                success=False,
                crm_lead_id=crm_lead_id,
                error_message=str(e)
            )

    def get_lead(self, crm_lead_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a contact from HubSpot by ID."""
        try:
            contact = self.client.crm.contacts.basic_api.get_by_id(
                contact_id=crm_lead_id,
                properties=['company', 'email', 'lifecyclestage', 'hs_lead_status']
            )

            return {
                'id': contact.id,
                'company': contact.properties.get('company'),
                'email': contact.properties.get('email'),
                'lifecycle_stage': contact.properties.get('lifecyclestage'),
                'lead_status': contact.properties.get('hs_lead_status'),
            }

        except Exception as e:
            logger.error(f"Failed to get HubSpot contact {crm_lead_id}: {e}")
            return None

    def search_lead(self, email: Optional[str] = None,
                   company: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search for a contact in HubSpot by email or company."""
        try:
            from hubspot.crm.contacts import PublicObjectSearchRequest, Filter, FilterGroup

            # Build search filters
            filters = []

            if email:
                filters.append(Filter(property_name='email', operator='EQ', value=email))

            if company:
                filters.append(Filter(property_name='company', operator='EQ', value=company))

            if not filters:
                return None

            # HubSpot requires filters to be in a filter group
            filter_group = FilterGroup(filters=filters)

            search_request = PublicObjectSearchRequest(
                filter_groups=[filter_group],
                properties=['company', 'email', 'lifecyclestage', 'hs_lead_status'],
                limit=1
            )

            results = self.client.crm.contacts.search_api.do_search(public_object_search_request=search_request)

            if results.total > 0:
                contact = results.results[0]
                portal_id = self.config.get('portal_id', 'YOUR_PORTAL_ID')

                return {
                    'id': contact.id,
                    'company': contact.properties.get('company'),
                    'email': contact.properties.get('email'),
                    'lifecycle_stage': contact.properties.get('lifecyclestage'),
                    'lead_status': contact.properties.get('hs_lead_status'),
                    'url': f"https://app.hubspot.com/contacts/{portal_id}/contact/{contact.id}"
                }

            return None

        except Exception as e:
            logger.error(f"Failed to search HubSpot contacts: {e}")
            return None

    def _map_to_hubspot(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map generic lead data to HubSpot contact properties.

        HubSpot uses predefined properties like 'company', 'email', 'lifecyclestage'.
        Custom properties must be created in HubSpot first.
        """
        hs_data = {
            'company': lead_data.get('Company'),
            'lifecyclestage': 'lead',
            'hs_lead_status': self._get_lead_status(lead_data.get('Rating', 'Cold')),
            'website': lead_data.get('Website'),
            'state': lead_data.get('State'),
            'description': lead_data.get('Description'),
        }

        # Add custom properties (must be created in HubSpot first)
        # Custom property names in HubSpot are typically lowercase with underscores
        custom_props = {
            'population': lead_data.get('Custom_Population__c'),
            'relevance_score': lead_data.get('Custom_Relevance_Score__c'),
            'lead_type': lead_data.get('Custom_Lead_Type__c'),
            'urgency_score': lead_data.get('Custom_Urgency_Score__c'),
            'deadline': lead_data.get('Custom_Deadline__c'),
            'existing_vendor': lead_data.get('Custom_Existing_Vendor__c'),
            'competitors': lead_data.get('Custom_Competitors__c'),
        }

        # Only include non-None properties
        for prop, value in custom_props.items():
            if value is not None:
                hs_data[prop] = value

        # Remove None values from main data
        hs_data = {k: v for k, v in hs_data.items() if v is not None}

        return hs_data

    def _get_lead_status(self, rating: str) -> str:
        """Map rating to HubSpot lead status."""
        status_map = {
            'Hot': 'NEW',
            'Warm': 'OPEN',
            'Cold': 'OPEN'
        }
        return status_map.get(rating, 'OPEN')
