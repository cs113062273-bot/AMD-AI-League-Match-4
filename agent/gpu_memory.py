"""Bound the resident allocator and reclaim unused cache under budget pressure."""
import math
import os

MIB = 1024 ** 2


def configure(torch, device):
    if device != 'cuda':
        return None
    fraction = float(os.getenv('APERTURE_GPU_MEMORY_FRACTION', '0.9'))
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError('APERTURE_GPU_MEMORY_FRACTION must be in (0,1]')
    free, total = torch.cuda.mem_get_info()
    # Leave space for display/driver activity and allocations outside PyTorch.
    # Both limits concern this process; no other process is modified.
    budget = min(int(total * fraction), free - 512 * MIB)
    if budget <= 0:
        raise RuntimeError('Insufficient free GPU memory for the resident model')
    effective = budget / total
    torch.cuda.memory.set_per_process_memory_fraction(effective)
    return {'requested_fraction': fraction, 'effective_fraction': effective,
            'budget_bytes': budget, 'free_at_start_bytes': free, 'total_bytes': total}


def reclaim(torch, budget):
    if budget is None:
        return False
    reserved = torch.cuda.memory_reserved()
    allocated = torch.cuda.memory_allocated()
    if reserved >= budget['budget_bytes'] * .85 and reserved - allocated >= 256 * MIB:
        # empty_cache releases unused allocator blocks, not live model tensors.
        torch.cuda.empty_cache()
        return True
    return False
