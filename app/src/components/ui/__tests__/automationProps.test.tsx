import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import Button from '../Button';
import Card from '../Card';
import ListItem from '../ListItem';
import TextField from '../TextField';

describe('automation accessibility props', () => {
  it('forwards testID and accessibility props through common controls', () => {
    const onPress = jest.fn();
    const { getByTestId } = render(
      <>
        <Button testID="button-id" accessibilityLabel="Stable button" title="Translated" onPress={onPress} />
        <TextField testID="field-id" accessibilityLabel="Stable field" value="value" />
        <ListItem testID="list-id" accessibilityLabel="Stable list item" label="Translated item" onPress={onPress} showArrow={false} />
        <Card testID="card-id" accessibilityLabel="Stable card"><></></Card>
      </>
    );

    expect(getByTestId('button-id').props.accessibilityLabel).toBe('Stable button');
    expect(getByTestId('field-id').props.accessibilityLabel).toBe('Stable field');
    expect(getByTestId('list-id').props.accessibilityLabel).toBe('Stable list item');
    expect(getByTestId('card-id').props.accessibilityLabel).toBe('Stable card');
    fireEvent.press(getByTestId('button-id'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
