# my-tracker

Ben's calorie, weight and lift tracker. A static site on GitHub Pages: plain HTML, CSS and JS, with no backend.

- `data/weights.csv`: date, weight, note
- `data/meals.csv`: date, meal, items, calories, protein, carbs, fat, fiber, sodium
- `data/lifts.csv`: date, lift, weight, reps, gym
- `data/pantry.csv`: foods kept at home, with macros per serving
- `config.js`: targets and goal (the one place to change them)

**This repo is public.** It holds no photos, keys or tokens. Progress photos stay on the phone, in IndexedDB.

## How the targets were worked out (Nov 2026)

Ben: male, 21, 6'1" (185 cm), 165 lb (74.8 kg), lifting 3–4×/week push/pull/legs, under 10k steps/day.

1. **BMR** (Mifflin-St Jeor): 10×74.8 + 6.25×185.4 − 5×21 + 5 ≈ **1,810 kcal**
2. **Maintenance**: BMR × 1.55 (moderately active) ≈ **2,800 kcal**
3. **Lean bulk**: +300 kcal → **3,100 kcal**, aiming for about 0.5 lb/week of gain
4. **Protein**: about 1 g/lb → **165 g**
5. **Fat**: about 25% of calories → **85 g**
6. **Carbs**: the rest → **420 g**
7. **Fibre** 40 g; **sodium** soft cap 3,000 mg

Rule for adjusting: compare weekly averages every 2 weeks. If gain is under 0.25 lb/week, add about 150 kcal. If it's over 0.75 lb/week, take off about 150 kcal.
