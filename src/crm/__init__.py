"""
CRM Integration Module

Provides unified interface for pushing leads to various CRM systems:
- Salesforce
- HubSpot
- Extensible to other CRMs

Each integration handles:
- Authentication
- Lead creation/update
- Field mapping
- Error handling and retries
"""

from .base import CRMProvider, CRMConfig, CRMSyncResult
from .salesforce import SalesforceProvider
from .hubspot import HubSpotProvider

__all__ = [
    'CRMProvider',
    'CRMConfig',
    'CRMSyncResult',
    'SalesforceProvider',
    'HubSpotProvider',
    'get_crm_provider'
]


def get_crm_provider(provider_name: str, config: dict) -> CRMProvider:
    """
    Factory function to get CRM provider instance.

    Args:
        provider_name: 'salesforce' or 'hubspot'
        config: Provider-specific configuration dictionary

    Returns:
        Configured CRM provider instance

    Raises:
        ValueError: If provider_name is not supported
    """
    providers = {
        'salesforce': SalesforceProvider,
        'hubspot': HubSpotProvider,
    }

    if provider_name.lower() not in providers:
        raise ValueError(f"Unsupported CRM provider: {provider_name}. "
                        f"Supported providers: {', '.join(providers.keys())}")

    return providers[provider_name.lower()](config)
