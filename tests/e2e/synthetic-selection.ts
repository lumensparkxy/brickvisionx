import type { Page } from '@playwright/test';

// Transport tests inject an original synthetic option only into their own DOM.
// Production keeps the ten curated sets; the fixture never represents a real set.
export async function selectSyntheticSet(page: Page) {
  const field = page.getByLabel('Your set number');
  await field.evaluate(element => {
    const option = document.createElement('option');
    option.value = '99999';
    option.textContent = '99999 - Synthetic transport fixture';
    (element as HTMLSelectElement).add(option);
  });
  await field.selectOption('99999');
}
