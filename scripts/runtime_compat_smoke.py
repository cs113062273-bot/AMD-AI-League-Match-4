"""Exercise the installed Qwen3 BF16/SDPA generation API; random tiny weights, not an accuracy test."""
import json
import argparse
import torch
from transformers import Qwen3Config, Qwen3ForCausalLM
from transformers import AutoModelForCausalLM
import tempfile


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cpu',action='store_true');args=ap.parse_args()
    if not args.cpu and not torch.cuda.is_available():raise RuntimeError('GPU unavailable')
    device='cpu' if args.cpu else 'cuda'
    config=Qwen3Config(vocab_size=128,hidden_size=64,intermediate_size=128,
        num_hidden_layers=2,num_attention_heads=4,num_key_value_heads=2,head_dim=16)
    config._attn_implementation='sdpa'
    with tempfile.TemporaryDirectory() as folder:
        Qwen3ForCausalLM(config).save_pretrained(folder)
        model=AutoModelForCausalLM.from_pretrained(folder,dtype=torch.float32 if args.cpu else torch.bfloat16,
            attn_implementation='sdpa',device_map={'':device},low_cpu_mem_usage=True,local_files_only=True).eval()
    ids=torch.tensor([[1,8,9]],device=device)
    with torch.inference_mode():
        output=model.generate(ids,max_new_tokens=4,do_sample=False,logits_to_keep=1,pad_token_id=0,eos_token_id=127)
    if not args.cpu:torch.cuda.synchronize()
    if output.shape[1]<=ids.shape[1]:raise RuntimeError('No generated tokens')
    print(json.dumps({'test':'random tiny Qwen3 compatibility; not answer quality','generated_tokens':output.shape[1]-ids.shape[1],
        'dtype':str(next(model.parameters()).dtype),'torch':torch.__version__,'hip':torch.version.hip,'device':'cpu' if args.cpu else torch.cuda.get_device_name()}))


if __name__=='__main__':main()
