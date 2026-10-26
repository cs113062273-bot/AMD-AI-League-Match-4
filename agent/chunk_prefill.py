"""Lossless Qwen3 prefix prefill; generation consumes the final prompt token."""


def prefill(model, inputs, torch, control, record, chunk_size=512):
    ids = inputs['input_ids']
    end_prefix = ids.shape[1] - 1
    mask = inputs.get('attention_mask')
    cache = None
    record['prefill_chunks'] = 0
    record['prefill_tokens'] = 0
    for start in range(0, end_prefix, chunk_size):
        control.check()
        end = min(start + chunk_size, end_prefix)
        output = model(input_ids=ids[:, start:end],
                       attention_mask=mask[:, :end] if mask is not None else None,
                       cache_position=torch.arange(start, end, device=ids.device),
                       past_key_values=cache, use_cache=True, logits_to_keep=1, return_dict=True)
        cache = output.past_key_values
        del output
        record['prefill_chunks'] += 1
        record['prefill_tokens'] = end
    control.check()
    return cache
