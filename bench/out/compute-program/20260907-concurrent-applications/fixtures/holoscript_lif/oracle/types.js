/**
 * @holoscript/snn-webgpu - Type Definitions
 *
 * Core types for the Spiking Neural Network WebGPU compute library.
 */
/** Spike encoding schemes. */
export var EncodingMode;
(function (EncodingMode) {
    /** Firing rate proportional to input magnitude. */
    EncodingMode[EncodingMode["Rate"] = 0] = "Rate";
    /** Spike time inversely proportional to input magnitude. */
    EncodingMode[EncodingMode["Temporal"] = 1] = "Temporal";
    /** Spikes on significant changes only. */
    EncodingMode[EncodingMode["Delta"] = 2] = "Delta";
})(EncodingMode || (EncodingMode = {}));
/** Spike decoding schemes. */
export var DecodingMode;
(function (DecodingMode) {
    /** Count spikes / time_window. */
    DecodingMode[DecodingMode["Rate"] = 0] = "Rate";
    /** Earliest spike time => value. */
    DecodingMode[DecodingMode["Temporal"] = 1] = "Temporal";
    /** Weighted average across population. */
    DecodingMode[DecodingMode["Population"] = 2] = "Population";
    /** Winner-take-all first spike. */
    DecodingMode[DecodingMode["FirstSpike"] = 3] = "FirstSpike";
})(DecodingMode || (DecodingMode = {}));
/**
 * Default LIF parameters based on standard neurophysiology.
 * Suitable for a general-purpose cortical neuron model.
 */
export const DEFAULT_LIF_PARAMS = {
    tau: 20.0,
    vThreshold: -55.0,
    vReset: -75.0,
    vRest: -65.0,
    dt: 1.0,
};
/** Default encoding parameters. */
export const DEFAULT_ENCODE_PARAMS = {
    timeWindow: 100,
    encodingMode: EncodingMode.Rate,
    seed: 42,
    minValue: 0.0,
    maxValue: 1.0,
    deltaThreshold: 0.1,
};
/** Default decoding parameters. */
export const DEFAULT_DECODE_PARAMS = {
    decodingMode: DecodingMode.Rate,
    populationSize: 10,
    outputMin: 0.0,
    outputMax: 1.0,
};
/** Compute the number of workgroups needed for N items at a given workgroup size. */
export function computeDispatchSize(count, workgroupSize = 256) {
    return Math.ceil(count / workgroupSize);
}
