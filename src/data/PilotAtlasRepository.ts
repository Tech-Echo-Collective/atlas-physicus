import pilotData from '../../pipeline/export/hep-th-pilot.json';
import { StaticAtlasRepository } from './StaticAtlasRepository';

/**
 * Real-data pilot adapter. The generated export crosses the same repository
 * boundary as the synthetic dataset, while remaining a separately loaded
 * browser chunk until a user selects the pilot.
 */
export const pilotAtlasRepository = new StaticAtlasRepository(pilotData);
