// One place for Ben's targets. The dashboard reads everything from here.
// How these were worked out is explained in README.md.
const CONFIG = {
  name: "Ben",
  units: "lb",
  startWeight: 165,
  goalWeight: 200,
  goalBand: [195, 205],      // shaded band on the weight chart
  targets: {
    calories: 3100,          // kcal / day (lean bulk: ~maintenance + 300)
    protein: 165,            // g / day (about 1 g per lb of body weight)
    carbs: 420,              // g / day
    fat: 85,                 // g / day
    fiber: 40,               // g / day
    sodium: 3000             // mg / day, soft cap
  },
  // Status pill rules for each day (checked in this order):
  status: {
    underBy: 200,            // "Under"         if calories < target - 200 (the main bulk risk)
    overBy: 300,             // "Over"          if calories > target + 300
    lowProtein: 0.75,        // "Low protein"   if protein < 75% of target
    proteinShort: 0.9        // "Protein short" if protein < 90% of target
  },                         // otherwise       "On target"
  split: ["Push", "Pull", "Legs"]
};
