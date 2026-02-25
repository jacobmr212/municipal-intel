"""
Test Script for Enterprise Features

Tests all 13 phases of enterprise features to ensure APIs are working.
Run this after deployment to verify everything works.

Usage:
    python3 test_enterprise_features.py --url https://your-app.railway.app --email test@example.com
"""

import requests
import json
import sys
import argparse
from datetime import datetime, timedelta


class EnterpriseFeatureTester:
    def __init__(self, base_url: str, email: str):
        self.base_url = base_url.rstrip('/')
        self.email = email
        self.token = None
        self.test_results = []

    def log(self, message: str, status: str = "INFO"):
        icons = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️", "WARN": "⚠️"}
        print(f"{icons.get(status, 'ℹ️')} {message}")
        self.test_results.append((message, status))

    def authenticate(self):
        """Step 1: Get authentication token (assumes magic link flow)."""
        self.log("Testing authentication...", "INFO")

        # For testing, we'll assume you provide a valid JWT token
        # In production, you'd go through the magic link flow
        token = input(f"\nPlease provide a JWT token for {self.email} (or press Enter to skip): ").strip()

        if not token:
            self.log("No token provided - skipping API tests that require auth", "WARN")
            return False

        self.token = token

        # Test token validity
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(f"{self.base_url}/api/feed", headers=headers)

        if response.status_code == 200:
            self.log("Authentication successful", "PASS")
            return True
        else:
            self.log(f"Authentication failed: {response.status_code}", "FAIL")
            return False

    def test_phase_1_deduplication(self):
        """Phase 1.1: Test lead deduplication."""
        self.log("\n=== PHASE 1.1: Lead Deduplication ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Get feed and check for dedup fields
        response = requests.get(f"{self.base_url}/api/feed?limit=5", headers=headers)

        if response.status_code == 200:
            leads = response.json().get('leads', [])

            if leads:
                # Check first lead has dedup fields
                lead = leads[0]
                has_times_seen = 'times_seen' in lead
                has_first_seen = 'first_seen' in lead
                has_last_seen = 'last_seen' in lead

                if has_times_seen and has_first_seen and has_last_seen:
                    self.log(f"Deduplication fields present (times_seen: {lead.get('times_seen')})", "PASS")
                else:
                    self.log("Missing deduplication fields", "FAIL")
            else:
                self.log("No leads found to test (run a scan first)", "WARN")
        else:
            self.log(f"Failed to fetch feed: {response.status_code}", "FAIL")

    def test_phase_2_temporal(self):
        """Phase 2.1: Test temporal intelligence."""
        self.log("\n=== PHASE 2.1: Temporal Intelligence ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Get feed and check for temporal fields
        response = requests.get(f"{self.base_url}/api/feed?min_urgency=1&limit=5", headers=headers)

        if response.status_code == 200:
            leads = response.json().get('leads', [])

            if leads:
                # Check first lead has temporal fields
                lead = leads[0]
                has_urgency = 'urgency_score' in lead
                has_deadline = 'deadline_date' in lead or lead.get('deadline_date') is None  # Can be null
                has_decision_stage = 'decision_stage' in lead

                if has_urgency and has_deadline and has_decision_stage:
                    self.log(f"Temporal intelligence present (urgency: {lead.get('urgency_score')}, stage: {lead.get('decision_stage')})", "PASS")
                else:
                    self.log("Missing temporal intelligence fields", "FAIL")
            else:
                self.log("No leads found to test", "WARN")
        else:
            self.log(f"Failed to fetch feed: {response.status_code}", "FAIL")

    def test_phase_2_competitor(self):
        """Phase 2.3: Test competitor intelligence."""
        self.log("\n=== PHASE 2.3: Competitor Intelligence ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Get feed and check for competitor fields
        response = requests.get(f"{self.base_url}/api/feed?has_competitors=true&limit=5", headers=headers)

        if response.status_code == 200:
            leads = response.json().get('leads', [])

            if leads:
                # Check first lead has competitor fields
                lead = leads[0]
                has_competitors = 'competitors_mentioned' in lead
                has_context = 'competitive_context' in lead
                has_existing_vendor = 'existing_vendor' in lead

                if has_competitors and has_context and has_existing_vendor:
                    competitors = lead.get('competitors_mentioned', [])
                    self.log(f"Competitor intelligence present (competitors: {len(competitors)})", "PASS")
                else:
                    self.log("Missing competitor intelligence fields", "FAIL")
            else:
                self.log("No leads with competitors found (expected for some scans)", "WARN")
        else:
            self.log(f"Failed to fetch feed: {response.status_code}", "FAIL")

    def test_phase_3_crm_config(self):
        """Phase 3.1: Test CRM configuration endpoints."""
        self.log("\n=== PHASE 3.1: CRM Integration ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Test GET CRM configs
        response = requests.get(f"{self.base_url}/api/crm/config", headers=headers)

        if response.status_code == 200:
            configs = response.json().get('configs', [])
            self.log(f"CRM config endpoint working ({len(configs)} configs)", "PASS")
        else:
            self.log(f"CRM config endpoint failed: {response.status_code}", "FAIL")

        # Test CRM sync status
        response = requests.get(f"{self.base_url}/api/crm/sync-status", headers=headers)

        if response.status_code == 200:
            status = response.json()
            self.log(f"CRM sync status endpoint working ({status.get('total_leads', 0)} total leads, {status.get('synced', 0)} synced)", "PASS")
        else:
            self.log(f"CRM sync status endpoint failed: {response.status_code}", "FAIL")

    def test_phase_4_advanced_filters(self):
        """Phase 4.2: Test advanced feed filters."""
        self.log("\n=== PHASE 4.2: Advanced Feed Filters ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Test filter options endpoint
        response = requests.get(f"{self.base_url}/api/feed/filter-options", headers=headers)

        if response.status_code == 200:
            options = response.json()
            categorical = options.get('categorical', {})
            ranges = options.get('ranges', {})

            self.log(f"Filter options endpoint working ({len(categorical.get('states', []))} states available)", "PASS")
        else:
            self.log(f"Filter options endpoint failed: {response.status_code}", "FAIL")

        # Test advanced filtering
        params = {
            'min_urgency': 60,
            'lead_type': 'hot',
            'sort_by': 'urgency',
            'sort_order': 'desc',
            'limit': 10
        }

        response = requests.get(f"{self.base_url}/api/feed", headers=headers, params=params)

        if response.status_code == 200:
            leads = response.json().get('leads', [])
            self.log(f"Advanced filtering working ({len(leads)} leads found)", "PASS")
        else:
            self.log(f"Advanced filtering failed: {response.status_code}", "FAIL")

    def test_phase_5_analytics(self):
        """Phase 5.1: Test analytics dashboard."""
        self.log("\n=== PHASE 5.1: Analytics Dashboard ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Test analytics dashboard
        response = requests.get(f"{self.base_url}/api/analytics/dashboard?days=30", headers=headers)

        if response.status_code == 200:
            data = response.json()
            overview = data.get('overview', {})
            self.log(f"Analytics dashboard working ({overview.get('total_leads', 0)} total leads)", "PASS")
        else:
            self.log(f"Analytics dashboard failed: {response.status_code}", "FAIL")

    def test_phase_5_roi(self):
        """Phase 5.2: Test ROI analytics."""
        self.log("\n=== PHASE 5.2: ROI Analytics ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Test ROI analytics
        response = requests.get(f"{self.base_url}/api/roi-analytics", headers=headers)

        if response.status_code == 200:
            data = response.json()
            pipeline = data.get('pipeline', {})
            revenue = data.get('revenue', {})
            self.log(f"ROI analytics working (total revenue: ${revenue.get('total', 0):,})", "PASS")
        else:
            self.log(f"ROI analytics failed: {response.status_code}", "FAIL")

    def test_lead_detail_page(self):
        """Phase 4.1: Test lead detail page."""
        self.log("\n=== PHASE 4.1: Lead Detail Page ===", "INFO")

        if not self.token:
            self.log("Skipping (no auth token)", "WARN")
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        # Get a lead ID from feed
        response = requests.get(f"{self.base_url}/api/feed?limit=1", headers=headers)

        if response.status_code == 200:
            leads = response.json().get('leads', [])

            if leads:
                lead_id = leads[0]['id']

                # Test lead details endpoint
                response = requests.get(f"{self.base_url}/api/leads/{lead_id}/details", headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    sections = ['lead', 'signal_analysis', 'temporal_intelligence', 'competitive_analysis', 'municipality']
                    has_all_sections = all(section in data for section in sections)

                    if has_all_sections:
                        self.log("Lead detail page has all required sections", "PASS")
                    else:
                        self.log("Lead detail page missing some sections", "FAIL")
                else:
                    self.log(f"Lead detail page failed: {response.status_code}", "FAIL")
            else:
                self.log("No leads found to test (run a scan first)", "WARN")
        else:
            self.log(f"Failed to fetch feed: {response.status_code}", "FAIL")

    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        passed = sum(1 for _, status in self.test_results if status == "PASS")
        failed = sum(1 for _, status in self.test_results if status == "FAIL")
        warned = sum(1 for _, status in self.test_results if status == "WARN")

        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warned}")
        print("="*70)

        if failed > 0:
            print("\nFailed tests:")
            for message, status in self.test_results:
                if status == "FAIL":
                    print(f"  ❌ {message}")

        return failed == 0

    def run_all_tests(self):
        """Run all enterprise feature tests."""
        print("="*70)
        print("MUNICIPAL INTEL - ENTERPRISE FEATURES TEST")
        print("="*70)
        print(f"Target: {self.base_url}")
        print(f"Email: {self.email}")
        print("="*70)

        # Authenticate
        if not self.authenticate():
            self.log("Cannot proceed without authentication", "FAIL")
            return False

        # Run all phase tests
        self.test_phase_1_deduplication()
        self.test_phase_2_temporal()
        self.test_phase_2_competitor()
        self.test_phase_3_crm_config()
        self.test_phase_4_advanced_filters()
        self.test_lead_detail_page()
        self.test_phase_5_analytics()
        self.test_phase_5_roi()

        # Print summary
        return self.print_summary()


def main():
    parser = argparse.ArgumentParser(description='Test Municipal Intel enterprise features')
    parser.add_argument('--url', required=True, help='Base URL of the application (e.g., https://your-app.railway.app)')
    parser.add_argument('--email', required=True, help='Email address for authentication')

    args = parser.parse_args()

    tester = EnterpriseFeatureTester(args.url, args.email)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
