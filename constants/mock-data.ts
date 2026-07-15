export const scannerResult = {
  itemName: 'Plastic Bottle',
  label: 'IDENTIFIED - PLASTIC BOTTLE',
  disposal: 'recycle.',
  materialTag: 'PETE 1 - High Impact',
  summary: 'Accepted at most curbside recycling programs when emptied and loosely capped.',
  steps: [
    'Remove the cap if your local program asks for caps to be separated.',
    'Empty any remaining liquid and rinse the bottle with cold water.',
    'Flatten the bottle slightly to save room in your recycling bin.',
  ],
  buttonLabel: 'Find Nearby Locations',
};

export const locationFilters = [
  { id: 'all', label: 'All Sites' },
  { id: 'recycling', label: 'Recycling' },
  { id: 'hazardous', label: 'Hazardous' },
  { id: 'donation', label: 'Donation' },
] as const;

export const nearbyLocations = [
  {
    id: 'eco-cycle-austin',
    type: 'Municipal Hub',
    name: 'EcoCycle Austin Central',
    address: '124 Greenway Dr, Austin, TX 78701',
    status: 'Open until 8 PM',
    distance: '1.2 mi',
    accent: '#88D39D',
    mapStyle: 'grid' as const,
  },
  {
    id: 'terraclean-solutions',
    type: 'Private Facility',
    name: 'TerraClean Solutions',
    address: '4502 Industrial Way, Austin, TX 78744',
    status: 'Closes soon - 5 PM',
    distance: '3.8 mi',
    accent: '#F2C572',
    mapStyle: 'building' as const,
  },
  {
    id: 'south-lamar-reuse',
    type: 'Neighborhood Drop-off',
    name: 'South Lamar ReUse Center',
    address: '2715 Bluebonnet Ln, Austin, TX 78704',
    status: 'Open until 6 PM',
    distance: '4.4 mi',
    accent: '#7FC6FF',
    mapStyle: 'pin' as const,
  },
];

export type MockScanThumbnailVariant = 'plastic-bottle' | 'cardboard-boxes' | 'aluminum-can';

export type MockScanHistoryItem = {
  id: string;
  itemName: string;
  disposalLabel: 'RECYCLE' | 'COMPOST' | 'TRASH';
  scannedAtLabel: string;
  thumbnailVariant: MockScanThumbnailVariant;
};

export type MockScanHistorySection = {
  id: string;
  title: string;
  items: MockScanHistoryItem[];
};

export const mockRecentScanSummary = {
  monthlyCount: 42,
  monthlySummary: "You've properly disposed of 42 items this month.",
};

export const mockRecentScanSections: MockScanHistorySection[] = [
  {
    id: 'today',
    title: 'Today',
    items: [
      {
        id: 'plastic-water-bottle',
        itemName: 'Plastic Water Bottle',
        disposalLabel: 'RECYCLE',
        scannedAtLabel: '10:42 AM',
        thumbnailVariant: 'plastic-bottle',
      },
    ],
  },
  {
    id: 'yesterday',
    title: 'Yesterday',
    items: [
      {
        id: 'cardboard-boxes',
        itemName: 'Cardboard Boxes',
        disposalLabel: 'RECYCLE',
        scannedAtLabel: '4:15 PM',
        thumbnailVariant: 'cardboard-boxes',
      },
      {
        id: 'aluminum-soda-can',
        itemName: 'Aluminum Soda Can',
        disposalLabel: 'RECYCLE',
        scannedAtLabel: '11:20 AM',
        thumbnailVariant: 'aluminum-can',
      },
    ],
  },
];

export type MockProfileSummary = {
  name: string;
  email: string;
  initials: string;
  membershipLabel: string;
  statusMessage: string;
  placeholderBadge: string;
  footnote: string;
};

export type MockProfileStat = {
  id: string;
  value: string;
  label: string;
  caption: string;
};

export type MockProfileOptionIconName =
  | 'location-outline'
  | 'notifications-outline'
  | 'color-palette-outline'
  | 'chatbubble-ellipses-outline'
  | 'help-circle-outline'
  | 'document-text-outline'
  | 'lock-closed-outline'
  | 'leaf-outline';

export type MockProfileOption = {
  id: string;
  title: string;
  description: string;
  value?: string;
  badge?: string;
  iconName: MockProfileOptionIconName;
};

export type MockProfileSection = {
  id: string;
  title: string;
  options: MockProfileOption[];
};

export const mockProfileSummary: MockProfileSummary = {
  name: 'Maya Johnson',
  email: 'maya@greenbin.mock',
  initials: 'MJ',
  membershipLabel: 'Community Member',
  statusMessage: 'Profile and account features will live here once sign-in and sync are ready.',
  placeholderBadge: 'Preview Only',
  footnote:
    'This is a placeholder account screen using mock data only. No authentication, sync, or cloud profile has been enabled yet.',
};

export const mockProfileStats: MockProfileStat[] = [
  {
    id: 'items-this-month',
    value: '42',
    label: 'This Month',
    caption: 'Items sorted correctly',
  },
  {
    id: 'recycle-rate',
    value: '86%',
    label: 'Recycle Rate',
    caption: 'Based on recent scans',
  },
  {
    id: 'nearby-checks',
    value: '12',
    label: 'Nearby Checks',
    caption: 'Drop-off lookups',
  },
];

export const mockProfileSections: MockProfileSection[] = [
  {
    id: 'preferences',
    title: 'Preferences',
    options: [
      {
        id: 'home-area',
        title: 'Home area',
        description: 'Austin, TX is set as your default place for future local guidance.',
        value: 'Mock',
        iconName: 'location-outline',
      },
      {
        id: 'scan-reminders',
        title: 'Scan reminders',
        description: 'Bin day nudges and streak reminders will appear here later.',
        badge: 'Soon',
        iconName: 'notifications-outline',
      },
      {
        id: 'appearance',
        title: 'App appearance',
        description: 'Theme and layout preferences will be managed from this section.',
        badge: 'Later',
        iconName: 'color-palette-outline',
      },
    ],
  },
  {
    id: 'help-and-feedback',
    title: 'Help and Feedback',
    options: [
      {
        id: 'feedback',
        title: 'Send feedback',
        description: 'Share ideas about scans, nearby guidance, and what should come next.',
        badge: 'Placeholder',
        iconName: 'chatbubble-ellipses-outline',
      },
      {
        id: 'help-center',
        title: 'Help center',
        description: 'FAQs, onboarding tips, and troubleshooting links can live here.',
        badge: 'Soon',
        iconName: 'help-circle-outline',
      },
    ],
  },
  {
    id: 'privacy-and-account',
    title: 'Privacy and Account',
    options: [
      {
        id: 'privacy',
        title: 'Privacy controls',
        description: 'Review scan history, data preferences, and export tools in the future.',
        badge: 'Planned',
        iconName: 'lock-closed-outline',
      },
      {
        id: 'account-settings',
        title: 'Account settings',
        description: 'Sign-in status, connected devices, and cloud sync will appear here later.',
        badge: 'No Auth Yet',
        iconName: 'document-text-outline',
      },
      {
        id: 'impact-summary',
        title: 'Impact summary',
        description: 'Monthly sustainability insights and habit snapshots will be surfaced here.',
        badge: 'Mock',
        iconName: 'leaf-outline',
      },
    ],
  },
];
