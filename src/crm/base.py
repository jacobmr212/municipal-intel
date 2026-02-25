"""
Base CRM Provider Interface

Defines abstract base class that all CRM integrations must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class CRMConfig:
    """Configuration for CRM provider."""
    provider_name: str  # 'salesforce' | 'hubspot'
    credentials: Dict[str, str]  # Provider-specific auth credentials
    field_mapping: Dict[str, str] = None  # Maps Lead model fields to CRM fields
    default_owner_id: Optional[str] = None  # Default CRM user ID for lead assignment
    enabled: bool = True


@dataclass
class CRMSyncResult:
    """Result of syncing a lead to CRM."""
    success: bool
    crm_lead_id: Optional[str] = None  # ID in the CRM system
    crm_url: Optional[str] = None  # Direct URL to view lead in CRM
    error_message: Optional[str] = None
    synced_at: datetime = None

    def __post_init__(self):
        if self.synced_at is None:
            self.synced_at = datetime.utcnow()


class CRMProvider(ABC):
    """
    Abstract base class for CRM integrations.

    All CRM providers must implement these methods.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize CRM provider with configuration.

        Args:
            config: Dictionary containing provider-specific configuration
        """
        self.config = config
        self._authenticated = False

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with the CRM system.

        Returns:
            True if authentication successful, False otherwise
        """
        pass

    @abstractmethod
    def create_lead(self, lead_data: Dict[str, Any]) -> CRMSyncResult:
        """
        Create a new lead in the CRM.

        Args:
            lead_data: Dictionary containing lead information

        Returns:
            CRMSyncResult with success status and CRM lead ID
        """
        pass

    @abstractmethod
    def update_lead(self, crm_lead_id: str, lead_data: Dict[str, Any]) -> CRMSyncResult:
        """
        Update an existing lead in the CRM.

        Args:
            crm_lead_id: CRM system's lead ID
            lead_data: Dictionary containing updated lead information

        Returns:
            CRMSyncResult with success status
        """
        pass

    @abstractmethod
    def get_lead(self, crm_lead_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a lead from the CRM by ID.

        Args:
            crm_lead_id: CRM system's lead ID

        Returns:
            Dictionary containing lead data, or None if not found
        """
        pass

    @abstractmethod
    def search_lead(self, email: Optional[str] = None,
                   company: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Search for a lead by email or company name.

        Args:
            email: Contact email
            company: Company/municipality name

        Returns:
            Dictionary containing lead data, or None if not found
        """
        pass

    def sync_lead(self, lead_data: Dict[str, Any], update_existing: bool = True) -> CRMSyncResult:
        """
        Sync a lead to CRM (create or update).

        Args:
            lead_data: Dictionary containing lead information
            update_existing: If True, update existing leads; if False, skip duplicates

        Returns:
            CRMSyncResult with sync status
        """
        if not self._authenticated:
            if not self.authenticate():
                return CRMSyncResult(
                    success=False,
                    error_message="Authentication failed"
                )

        # Check if lead already exists
        existing = self.search_lead(
            company=lead_data.get('Company') or lead_data.get('municipality')
        )

        if existing:
            if update_existing:
                return self.update_lead(existing['id'], lead_data)
            else:
                return CRMSyncResult(
                    success=True,
                    crm_lead_id=existing['id'],
                    crm_url=existing.get('url'),
                    error_message="Lead already exists (skipped update)"
                )

        # Create new lead
        return self.create_lead(lead_data)

    def map_lead_data(self, lead: Any) -> Dict[str, Any]:
        """
        Map Lead model instance to CRM field format.

        Args:
            lead: Lead model instance from database

        Returns:
            Dictionary with CRM-formatted fields
        """
        # Default mapping - can be overridden by subclasses
        return {
            'Company': f"{lead.municipality}, {lead.state}",
            'Title': lead.title,
            'LeadSource': 'Municipal Intel Scanner',
            'Description': self._build_description(lead),
            'Status': 'New',
            'Rating': self._get_lead_rating(lead),
            'Website': lead.url,
            'State': lead.state,
            'Custom_Population__c': lead.population,
            'Custom_Relevance_Score__c': lead.relevance_score,
            'Custom_Lead_Type__c': lead.lead_type,
            'Custom_Urgency_Score__c': lead.urgency_score,
            'Custom_Deadline__c': lead.deadline_date,
            'Custom_Existing_Vendor__c': lead.existing_vendor,
            'Custom_Competitors__c': ', '.join(lead.competitors_mentioned) if lead.competitors_mentioned else None,
        }

    def _build_description(self, lead: Any) -> str:
        """Build detailed description from lead data."""
        parts = []

        parts.append(f"Municipality: {lead.municipality}, {lead.state} (pop: {lead.population:,})")
        parts.append(f"Lead Type: {lead.lead_type.upper()}")
        parts.append(f"Relevance Score: {lead.relevance_score:.1f}/100")

        if lead.urgency_score > 0:
            parts.append(f"Urgency: {lead.urgency_score}/100")

        if lead.deadline_date:
            parts.append(f"Deadline: {lead.deadline_date}")

        if lead.decision_stage:
            parts.append(f"Decision Stage: {lead.decision_stage}")

        if lead.existing_vendor:
            parts.append(f"Current Vendor: {lead.existing_vendor}")

        if lead.competitors_mentioned:
            parts.append(f"Competitors: {', '.join(lead.competitors_mentioned[:3])}")

        if lead.customer_status == 'existing_customer':
            parts.append("⚠️ EXISTING CUSTOMER - retention/upsell opportunity")

        parts.append(f"\nSource: {lead.source_type}")
        parts.append(f"Document: {lead.title}")
        parts.append(f"URL: {lead.url}")

        if lead.recommended_action:
            parts.append(f"\nRecommended Action: {lead.recommended_action}")

        return '\n'.join(parts)

    def _get_lead_rating(self, lead: Any) -> str:
        """Convert lead type to CRM rating."""
        rating_map = {
            'hot': 'Hot',
            'warm': 'Warm',
            'cold': 'Cold'
        }
        return rating_map.get(lead.lead_type, 'Cold')
