const inner = @import("core/queue/wgpu_ffi_sync.zig");

pub const syncAfterSubmit = inner.syncAfterSubmit;
pub const submitEmpty = inner.submitEmpty;
pub const submitCommandBuffers = inner.submitCommandBuffers;
pub const submitInternal = inner.submitInternal;
pub const flushQueue = inner.flushQueue;
pub const waitForQueue = inner.waitForQueue;
pub const waitForQueueOnce = inner.waitForQueueOnce;
pub const shouldRetryQueueWait = inner.shouldRetryQueueWait;
pub const waitForQueueProcessEvents = inner.waitForQueueProcessEvents;
pub const waitForQueueWaitAny = inner.waitForQueueWaitAny;
pub const readTimestampBuffer = inner.readTimestampBuffer;
pub const readTimestampBufferOnce = inner.readTimestampBufferOnce;
pub const shouldRetryTimestampMap = inner.shouldRetryTimestampMap;
pub const processEventsUntil = inner.processEventsUntil;
