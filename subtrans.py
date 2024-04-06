#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @author: loricheung

import os
import argparse
import subprocess
import math
from getpass import getpass
from typing import Union

from openai import OpenAI
import pysubs2
from pysubs2 import Alignment, Color, SSAFile, SSAStyle


def is_valid_key(key: str):
    if not key.startswith("sk-") or len(key) != 51:
        return False
    return True


if "OPENAI_API_KEY" in os.environ:
    api_key = os.environ["OPENAI_API_KEY"]
else:
    while True:
        api_key = getpass("输入你的OpenAI API Key: ")
        if is_valid_key(api_key):
            break
        else:
            print("无效的API Key. 请重试")

openai_client = OpenAI(api_key=api_key, timeout=180.0, max_retries=5)

index_lang = {}


def pprint(sub_streams: str) -> None:
    sub_streams_count = len(sub_streams.split(sep="\n")) - 1
    print(f"该视频文件共有{sub_streams_count}条字幕")
    print(f"{'索引':^4} | {'语言':^4} | {'样式':^28} |  {'字幕时长':^16}")
    for line in sub_streams.splitlines():
        parts = line.split(",")
        print(f"{'-'*6} | {'-'*6} | {'-'*30} | {'-'*20}")
        print(f"{parts[0]:^6} | {parts[1]:^6} | {parts[2]:^30} | {parts[3]:^20}")
        index_lang[parts[0]] = parts[1]


class SubtitleGenerator(object):
    def __init__(
        self,
        video: str,
        target_lang: str = "简体中文",
        max_split: int = 80,
        output_dir: str | None = None,
    ):
        self.video = video
        self.video_name = ".".join(video.split(".")[:-1])
        self.max_split = max_split
        self.target_lang = target_lang
        self.target_subtitle = SSAFile()
        self.output_dir = output_dir

    def extract(self) -> Union[str, None]:
        self.input_dir = os.path.dirname(os.path.abspath(self.video))
        output = subprocess.check_output(
            [
                "ffprobe",
                "-loglevel",
                "error",
                "-select_streams",
                "s",
                "-show_entries",
                "stream=index:stream_tags=language:stream_tags=DURATION:stream_tags=codec_name:stream_tags=title",
                "-of",
                "csv=p=0",
                f"{self.video}",
            ]
        )
        if not output:
            print("\n当前视频没有内置软字幕")
            return None

        sub_streams = output.decode()
        pprint(sub_streams)

        index = input("选择字幕流: ")
        target_sub_file = os.path.join(self.input_dir, f"{self.video_name}.srt")
        if self.output_dir:
            target_sub_file = os.path.join(
                os.path.abspath(self.output_dir), f"{self.video_name}.srt"
            )
        print("抽取已选择的字幕流 ... ", end="")

        out_sub = subprocess.check_output(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-i",
                f"{self.video}",
                "-map",
                f"0:{index}",
                f"{target_sub_file}",
                "-y",
            ]
        )

        if out_sub:
            print(f"抽取字幕时发生错误: {out_sub}")
            return None
        print("OK!")
        return target_sub_file

    def load(self, subtitle_file: str) -> None:
        subtile = pysubs2.load(subtitle_file)
        self.source_subtitle = subtile
        os.remove(subtitle_file)

    def split(self, subtitle: SSAFile, start: int) -> SSAFile:
        slices_subtitle = SSAFile()
        subtitle_length = len(subtitle)

        if start + self.max_split < subtitle_length:
            slices_subtitle.extend(subtitle[start : start + self.max_split])
        else:
            slices_subtitle.extend(subtitle[start : subtitle_length - 1])
        return slices_subtitle

    def merge(self, slices_subtitle: SSAFile) -> None:
        self.target_subtitle.extend(slices_subtitle)

    def translate(self, subtitle: SSAFile) -> str:
        subtitle_content = subtitle.to_string("srt")
        completion = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": f"你是一个专业的电影字幕翻译人员, 擅长从各种语言翻译为中文. 用户会将带有时间轴信息的字幕发送给你, 你要先完整理解字幕内容, 然后保留字幕的序列号和时间轴信息, 将字幕翻译为{self.target_lang}. 要求: 1,保持输出内容格式和输入内容格式相同.2,保留字幕中的人名和专有名词和缩写.3,输出内容要符合中文使用习惯,也要符合上下文.4,确保不要遗漏字幕.5,翻译完成后校验原始字幕和翻译字幕的最后3条的序列号,时间轴和字幕意思是否相同.如果不同,请重新翻译.6,不要输出校验结果到字幕内, 否则你会被罚款100美元.7,遵守以上所有要求,完成后你将得到1000美元的奖励",
                },
                {
                    "role": "user",
                    "content": f"```{subtitle_content}```",
                },
            ],
        )
        translated_content = (
            completion.choices[0].message.content.encode("utf-8").decode()  # type: ignore
        )
        return translated_content

    def split_and_translate(self):
        frag = math.ceil(len(self.source_subtitle) / self.max_split)
        for index in range(0, len(self.source_subtitle), self.max_split):
            print(f"\rHold my beer ... {(index // self.max_split) + 1}/{frag}", end="")
            slices_subtitle = self.split_and_translate_chunk(index)
            self.merge(slices_subtitle)
        print("\rHold my beer ... Done!")

    def split_and_translate_chunk(self, start: int) -> SSAFile:
        slices_subtitle = self.split(self.source_subtitle, start)
        translated_subtitle_string = self.translate(slices_subtitle)
        translated_subtitle = SSAFile.from_string(translated_subtitle_string)
        return translated_subtitle

    def generate_ass(self) -> None:
        print("生成ass字幕文件 ... ", end="")
        subs = SSAFile()
        subs.styles = {
            "bottom": SSAStyle(
                fontsize=16,
                outline=1,
                shadow=0.5,
                alignment=Alignment.BOTTOM_CENTER,
                primarycolor=Color(240, 240, 240),
                secondarycolor=Color(0, 0, 0),
                outlinecolor=Color(0, 0, 0),
            ),
            "top": SSAStyle(
                fontsize=16,
                outline=1,
                shadow=0.5,
                alignment=Alignment.BOTTOM_CENTER,
                primarycolor=Color(240, 240, 240),
                secondarycolor=Color(0, 0, 0),
                outlinecolor=Color(0, 0, 0),
            ),
        }
        for e in self.source_subtitle:
            e.style = "bottom"
            subs.append(e)
        for e in self.target_subtitle:
            e.style = "bottom"
            subs.append(e)

        output_dir = os.path.dirname(self.video)
        if self.output_dir:
            output_dir = self.output_dir
        else:
            output_dir = self.input_dir
        subs.save(os.path.join(output_dir, f"{self.video_name}.ass"))
        print("OK!")


def main():
    parser = argparse.ArgumentParser(
        description="抽取视频字幕流, 使用OpenAI GPT-3.5翻译, 生成目标语言的字幕"
    )
    parser.add_argument(
        "-v, --video", type=str, dest="video", required=True, help="视频文件路径"
    )
    parser.add_argument(
        "-t, --target-lang",
        type=str,
        dest="targetlang",
        default="简体中文",
        help="字幕目标语言",
    )
    parser.add_argument(
        "-n, --max-split",
        type=int,
        dest="maxsplit",
        default=80,
        help="由于翻译模型的输出token限制,需要将字幕分隔后进行翻译. 建议不超过100. 过大会超出token限制, 过小会增加翻译时间.",
    )
    parser.add_argument(
        "-o, --output-dir",
        type=str,
        dest="outputdir",
        default=None,
        help="输出字幕文件所在目录",
    )

    args = parser.parse_args()

    subtitle_generator = SubtitleGenerator(
        args.video,
        target_lang=args.targetlang,
        max_split=args.maxsplit,
        output_dir=args.outputdir,
    )

    subtitle_file = subtitle_generator.extract()
    if not subtitle_file:
        print("没有字幕文件被导出")
        return
    subtitle_generator.load(subtitle_file=subtitle_file)
    subtitle_generator.split_and_translate()
    subtitle_generator.generate_ass()


if __name__ == "__main__":
    main()
