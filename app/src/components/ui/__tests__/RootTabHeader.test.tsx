import React from 'react';
import { Text } from 'react-native';
import { render } from '@testing-library/react-native';

import RootTabHeader from '../RootTabHeader';

describe('RootTabHeader', () => {
  it('renders the shared root title, subtitle, brand mark and action', () => {
    const { getByText, getByTestId } = render(
      <RootTabHeader
        title="Charging stations"
        subtitle="Find a suitable charger"
        showBrandMark
        rightAction={<Text>Refresh</Text>}
        testID="test-root-header"
      />,
    );

    expect(getByText('Charging stations')).toBeTruthy();
    expect(getByText('Find a suitable charger')).toBeTruthy();
    expect(getByText('Refresh')).toBeTruthy();
    expect(getByTestId('test-root-header-brand')).toBeTruthy();
  });

  it('does not repeat the brand mark on non-home tabs', () => {
    const { queryByTestId } = render(
      <RootTabHeader title="Saved" testID="saved-root-header" />,
    );

    expect(queryByTestId('saved-root-header-brand')).toBeNull();
  });
});
