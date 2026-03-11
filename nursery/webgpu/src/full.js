import full from './index.js';
import { doe } from './doe.js';

export * from './index.js';
export { doe };

export default {
  ...full,
  doe,
};
