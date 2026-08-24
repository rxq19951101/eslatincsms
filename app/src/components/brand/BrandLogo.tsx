import React from 'react';
import { Image, type ImageProps } from 'react-native';

type BrandLogoProps = Omit<ImageProps, 'source'> & {
  compact?: boolean;
};

/** Official artwork exported with transparency from EsLatin 定稿2.ai. */
const BrandLogo: React.FC<BrandLogoProps> = ({
  compact = false,
  accessibilityLabel = 'EsLatin',
  resizeMode = 'contain',
  ...props
}) => (
  <Image
    {...props}
    source={
      compact
        ? require('../../../assets/eslatin-brand-compact.png')
        : require('../../../assets/eslatin-brand-transparent.png')
    }
    resizeMode={resizeMode}
    accessibilityLabel={accessibilityLabel}
  />
);

export default BrandLogo;
