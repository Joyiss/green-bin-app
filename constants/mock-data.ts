export const scannerResult = {
  itemName: 'Plastic Bottle',
  label: 'IDENTIFIED • PLASTIC BOTTLE',
  disposal: 'recycle.',
  materialTag: 'PETE 1 • High Impact',
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
    status: 'Closes soon • 5 PM',
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
