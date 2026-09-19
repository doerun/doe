#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include "d3d12_bridge.h"
typedef int32_t HRESULT;
typedef uint64_t UINT64;
#define DXGI_ERROR_DEVICE_REMOVED ((HRESULT)-2)
#define DXGI_ERROR_DEVICE_RESET ((HRESULT)-3)
#define FAILED(hr) ((hr) < 0)
#define SUCCEEDED(hr) ((hr) >= 0)
typedef struct { size_t Begin, End; } D3D12_RANGE;
typedef struct ID3D12CommandQueue ID3D12CommandQueue;
typedef struct { HRESULT (*GetTimestampFrequency)(ID3D12CommandQueue*, UINT64*); } QueueVtbl;
struct ID3D12CommandQueue { const QueueVtbl* lpVtbl; };
typedef struct ID3D12Resource ID3D12Resource;
typedef struct {
    HRESULT (*Map)(ID3D12Resource*, unsigned, const D3D12_RANGE*, void**);
    void (*Unmap)(ID3D12Resource*, unsigned, const D3D12_RANGE*);
} ResourceVtbl;
struct ID3D12Resource { const ResourceVtbl* lpVtbl; };
