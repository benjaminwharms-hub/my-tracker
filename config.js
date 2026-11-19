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
  split: ["Push", "Pull", "Legs"]
};
