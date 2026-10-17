"""Offline tooling; never invokes Studio's creative-review models."""
import argparse
from .core import train, read_json, write_json, fingerprint
from .workflow import comparison_report, transcript_quality, segment_report, creator_export, ablation_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    for name in ("fit","diagnose","transcript-quality","ablations"):
        p=commands.add_parser(name);p.add_argument("manifest");p.add_argument("output")
    p=commands.add_parser("segments")
    for name in ("predictions","calibration","clips","rules","output"):p.add_argument(name)
    p=commands.add_parser("creator-export");p.add_argument("reviewed_report");p.add_argument("output")
    p=commands.add_parser("approve",help="Human reviewer attests to the exact transcript and suggestion content")
    p.add_argument("report");p.add_argument("flag_id");p.add_argument("--reviewer",required=True);p.add_argument("--language",required=True)
    args=parser.parse_args()
    try:
        if args.command=="fit":train(args.manifest,args.output)
        elif args.command=="diagnose":comparison_report(args.manifest,args.output)
        elif args.command=="transcript-quality":transcript_quality(args.manifest,args.output)
        elif args.command=="ablations":ablation_report(args.manifest,args.output)
        elif args.command=="segments":segment_report(args.predictions,args.calibration,args.clips,args.rules,args.output)
        elif args.command=="creator-export":creator_export(args.reviewed_report,args.output)
        else:
            report=read_json(args.report)
            if args.language!=report["language"] or not args.reviewer.strip():raise ValueError("Reviewer identity and report language must match")
            found=False
            for clip in report["clips"]:
                for flag in clip["flags"]:
                    if flag["id"]!=args.flag_id:continue
                    if not flag.get("native_suggestion") or not flag.get("original_transcript"):raise ValueError("Provide a native suggestion and original transcript before approval")
                    content={k:flag.get(k) for k in ("id","original_transcript","native_suggestion","english_explanation","guideline_id")}
                    content.update(start=clip["start"],end=clip["end"],video_sha256=report["video_sha256"],guideline_version=report["guideline_version"])
                    flag["native_review"]={"reviewer":args.reviewer,"language":args.language,"approved":True,"content_sha256":fingerprint(content)}
                    found=True
            if not found:raise ValueError("Unknown flag ID")
            write_json(args.report,report)
    except (ValueError,KeyError,OSError) as exc:
        parser.exit(2,f"Not completed: {exc}\n")
    print("Completed. Synthetic tests are not evidence of human-rating agreement.")


if __name__=="__main__":main()
