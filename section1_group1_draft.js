// Section 1: Organization Profile - REBUILD
// Group 1: Identity & Scale (Q1-Q5)
// Total: 22 questions across 4 groups

const STATES_FULL = [
  { value: 'AL', label: 'Alabama' },
  { value: 'AK', label: 'Alaska' },
  { value: 'AZ', label: 'Arizona' },
  { value: 'AR', label: 'Arkansas' },
  { value: 'CA', label: 'California' },
  { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' },
  { value: 'DE', label: 'Delaware' },
  { value: 'FL', label: 'Florida' },
  { value: 'GA', label: 'Georgia' },
  { value: 'HI', label: 'Hawaii' },
  { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' },
  { value: 'IN', label: 'Indiana' },
  { value: 'IA', label: 'Iowa' },
  { value: 'KS', label: 'Kansas' },
  { value: 'KY', label: 'Kentucky' },
  { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' },
  { value: 'MD', label: 'Maryland' },
  { value: 'MA', label: 'Massachusetts' },
  { value: 'MI', label: 'Michigan' },
  { value: 'MN', label: 'Minnesota' },
  { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' },
  { value: 'MT', label: 'Montana' },
  { value: 'NE', label: 'Nebraska' },
  { value: 'NV', label: 'Nevada' },
  { value: 'NH', label: 'New Hampshire' },
  { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' },
  { value: 'NY', label: 'New York' },
  { value: 'NC', label: 'North Carolina' },
  { value: 'ND', label: 'North Dakota' },
  { value: 'OH', label: 'Ohio' },
  { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' },
  { value: 'PA', label: 'Pennsylvania' },
  { value: 'RI', label: 'Rhode Island' },
  { value: 'SC', label: 'South Carolina' },
  { value: 'SD', label: 'South Dakota' },
  { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' },
  { value: 'UT', label: 'Utah' },
  { value: 'VT', label: 'Vermont' },
  { value: 'VA', label: 'Virginia' },
  { value: 'WA', label: 'Washington' },
  { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' },
  { value: 'WY', label: 'Wyoming' },
  { value: 'DC', label: 'District of Columbia' }
];

const ENTITY_TYPES = [
  { value: 'city', label: 'City' },
  { value: 'town', label: 'Town' },
  { value: 'county', label: 'County' },
  { value: 'village', label: 'Village' },
  { value: 'borough', label: 'Borough' },
  { value: 'special_district', label: 'Special District', hasTextField: true, textPlaceholder: 'What type? (e.g., water, fire, transit)' },
  { value: 'tribal_government', label: 'Tribal Government' },
  { value: 'school_district', label: 'School District' },
  { value: 'regional_authority', label: 'Regional Authority' }
];

const GOVERNANCE_STRUCTURES = [
  { value: 'mayor_council_strong', label: 'Mayor-Council (Strong Mayor)' },
  { value: 'mayor_council_weak', label: 'Mayor-Council (Weak Mayor)' },
  { value: 'council_manager', label: 'Council-Manager' },
  { value: 'commission', label: 'Commission' },
  { value: 'town_meeting', label: 'Town Meeting' },
  { value: 'other', label: 'Other', hasTextField: true, textPlaceholder: 'Please specify' }
];

// Track current question number and special field values
let currentQuestionNumber = 1;
const totalQuestions = 22;
let specialDistrictType = '';
let otherGovernanceType = '';

// Helper: Get population tier
function getPopulationTier(pop) {
  const p = parseInt(pop);
  if (p < 2500) return 'Micro municipality';
  if (p < 10000) return 'Small municipality';
  if (p < 25000) return 'Small-mid municipality';
  if (p < 50000) return 'Mid-size municipality';
  if (p < 100000) return 'Large municipality';
  return 'Major municipality';
}

// Start the conversation - CONSOLIDATED MESSAGE
setTimeout(() => {
  addMessage('assistant', 'Welcome to Section 1! This section helps us understand your organization\'s basic information. It takes about 10-15 minutes, and you can save and come back anytime. Let\'s get started.');

  setTimeout(() => {
    currentStep = 'q1_state';
    addMessage('assistant', `Question ${currentQuestionNumber} of ${totalQuestions}: Which state is your organization located in?`, 'select', {
      options: STATES_FULL
    });
  }, 600);
}, 500);

// Handle user input
window.handleUserInput = function(step, value) {

  // Q1: State
  if (step === 'q1_state') {
    const stateName = STATES_FULL.find(s => s.value === value)?.label || value;

    setTimeout(() => {
      addMessage('assistant', `Got it — ${stateName}.`);

      setTimeout(() => {
        currentQuestionNumber = 2;
        currentStep = 'q2_entity_type';
        addMessage('assistant', `Question ${currentQuestionNumber} of ${totalQuestions}: What type of government entity are you?`, 'choice-buttons', {
          options: ENTITY_TYPES
        });
      }, 500);
    }, 400);
  }

  // Q2: Entity Type
  else if (step === 'q2_entity_type') {
    const entityLabel = ENTITY_TYPES.find(e => e.value === value)?.label || value;

    // If special district, need sub-question
    if (value === 'special_district') {
      setTimeout(() => {
        currentStep = 'q2_special_district_type';
        addMessage('assistant', 'What type of special district?', 'text-input', {
          inputType: 'text',
          placeholder: 'e.g., water, fire, transit'
        });
      }, 400);
      return;
    }

    setTimeout(() => {
      currentQuestionNumber = 3;
      currentStep = 'q3_organization_name';
      addMessage('assistant', `Question ${currentQuestionNumber} of ${totalQuestions}: What is the name of your organization?`, 'text-input', {
        inputType: 'text',
        placeholder: 'e.g., City of Eagle, Town of Vail'
      });
    }, 400);
  }

  // Q2 sub: Special district type
  else if (step === 'q2_special_district_type') {
    specialDistrictType = value;
    answers['entity_type_detail'] = value;

    setTimeout(() => {
      currentQuestionNumber = 3;
      currentStep = 'q3_organization_name';
      addMessage('assistant', `Question ${currentQuestionNumber} of ${totalQuestions}: What is the name of your organization?`, 'text-input', {
        inputType: 'text',
        placeholder: 'e.g., Eagle Water District'
      });
    }, 400);
  }

  // Q3: Organization Name
  else if (step === 'q3_organization_name') {
    setTimeout(() => {
      addMessage('assistant', `Welcome, ${value}.`);

      setTimeout(() => {
        currentQuestionNumber = 4;
        currentStep = 'q4_population';
        addMessage('assistant', `Question ${currentQuestionNumber} of ${totalQuestions}: What is the approximate population you serve?`, 'text-input', {
          inputType: 'number',
          placeholder: 'e.g., 15000'
        });
      }, 500);
    }, 400);
  }

  // Q4: Population
  else if (step === 'q4_population') {
    const pop = parseInt(value);
    const tier = getPopulationTier(pop);

    setTimeout(() => {
      addMessage('assistant', `${pop.toLocaleString()} — ${tier}. That gives me a good baseline for complexity.`);

      setTimeout(() => {
        currentQuestionNumber = 5;
        currentStep = 'q5_governance';
        addMessage('assistant', `Question ${currentQuestionNumber} of ${totalQuestions}: What is your governance structure?\\n\\nCouncil-Manager means you have a hired city/town manager. Strong Mayor means the mayor has executive authority and can veto council actions.`, 'choice-buttons', {
          options: GOVERNANCE_STRUCTURES
        });
      }, 600);
    }, 400);
  }

  // Q5: Governance Structure
  else if (step === 'q5_governance') {
    const govLabel = GOVERNANCE_STRUCTURES.find(g => g.value === value)?.label || value;

    // If "Other", need sub-question
    if (value === 'other') {
      setTimeout(() => {
        currentStep = 'q5_governance_other';
        addMessage('assistant', 'Please specify your governance structure:', 'text-input', {
          inputType: 'text',
          placeholder: 'e.g., Modified commission'
        });
      }, 400);
      return;
    }

    setTimeout(() => {
      addMessage('assistant', `${govLabel} — noted.`);

      setTimeout(() => {
        // GROUP 1 COMPLETE - Show transition to Group 2
        addMessage('assistant', '--- Group 1 complete: Identity & Scale ---\\n\\nNow let\'s look at your operations.');

        setTimeout(() => {
          // This is where Group 2 would start
          // For now, end the section
          addMessage('assistant', 'Group 1 proof of concept complete. Group 2 (Operational Footprint) will continue from here.');

          setTimeout(() => {
            saveProgress('in-progress');
            setTimeout(() => {
              window.location.href = '/app';
            }, 2000);
          }, 1000);
        }, 800);
      }, 500);
    }, 400);
  }

  // Q5 sub: Other governance type
  else if (step === 'q5_governance_other') {
    otherGovernanceType = value;
    answers['governance_structure_detail'] = value;

    setTimeout(() => {
      addMessage('assistant', `${value} — noted.`);

      setTimeout(() => {
        addMessage('assistant', '--- Group 1 complete: Identity & Scale ---\\n\\nNow let\'s look at your operations.');

        setTimeout(() => {
          addMessage('assistant', 'Group 1 proof of concept complete. Group 2 (Operational Footprint) will continue from here.');

          setTimeout(() => {
            saveProgress('in-progress');
            setTimeout(() => {
              window.location.href = '/app';
            }, 2000);
          }, 1000);
        }, 800);
      }, 500);
    }, 400);
  }

  // Update progress bar
  updateProgress((currentQuestionNumber / totalQuestions) * 100);

  // Auto-save
  saveProgress();
};
