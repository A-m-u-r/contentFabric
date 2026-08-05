const STANDARD_BADGE = {
  label: 'STANDARD',
  className: 'bg-blue-500 text-white',
};

const VIDEO_MODE_BADGES = {
  lowcost: {
    label: 'LOW COST',
    className: 'bg-green-500 text-black',
  },
  standard: STANDARD_BADGE,
  premium: {
    label: 'PREMIUM',
    className: 'bg-violet-500 text-white',
  },
  storyboard_v3_standard: STANDARD_BADGE,
  storyboard_v3_pro: {
    label: 'PRO',
    className: 'bg-violet-500 text-white',
  },
  storyboard_veo31_quality: {
    label: 'VEO 3.1',
    className: 'bg-amber-500 text-black',
  },
};

export function galleryVideoModeBadge(mode) {
  const normalizedMode = String(mode || '').trim().toLowerCase();
  return VIDEO_MODE_BADGES[normalizedMode] || STANDARD_BADGE;
}
