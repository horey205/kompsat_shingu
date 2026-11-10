#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국토정보위성 자동 처리 GUI
사용자 친화적인 Windows 인터페이스 (Thread-Safe Architecture)
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import os
import sys
import threading
import queue
from datetime import datetime
import subprocess
import shutil
import glob
import configparser

# Import local processor
try:
    from .processor import KompsatProcessor
    GDAL_AVAILABLE = True
    GDAL_ERROR = None
except ImportError:
    try:
        from processor import KompsatProcessor
        GDAL_AVAILABLE = True
        GDAL_ERROR = None
    except ImportError as e2:
        GDAL_AVAILABLE = False
        GDAL_ERROR = str(e2)

class KompsatGUI:
    """KOMPSAT 처리 GUI 클래스"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("국토정보위성 자동 처리 시스템 v2.0")
        self.root.geometry("920x720")
        self.root.resizable(True, True)
        
        # 스레드 안전 메시지 큐
        self.msg_queue = queue.Queue()
        
        # 설정 및 변수
        self.selected_folders = []
        self.is_processing = False
        self.qgis_path_var = tk.StringVar()
        self.settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.ini')
        self.load_settings()
        
        # UI 구성
        self.setup_ui()
        
        # 주기적 큐 폴링 시작 (스레드 안전 UI 업데이트)
        self.root.after(100, self.process_queue)
        
    def setup_ui(self):
        """UI 구성"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 타이틀
        title_label = ttk.Label(
            main_frame, 
            text="국토정보위성(CAS500-1) 자동 처리 시스템 v2.0",
            font=("맑은 고딕", 15, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 15))
        
        # === 입력 섹션 ===
        input_frame = ttk.LabelFrame(main_frame, text="입력 폴더 선택", padding="10")
        input_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 단일 폴더 선택
        ttk.Label(input_frame, text="단일 폴더:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.single_folder_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.single_folder_var, width=65).grid(
            row=0, column=1, padx=5, pady=5
        )
        ttk.Button(input_frame, text="찾아보기", command=self.browse_single_folder).grid(
            row=0, column=2, padx=5, pady=5
        )
        
        # 배치 처리 (루트 폴더)
        ttk.Label(input_frame, text="배치 처리 (루트):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.batch_folder_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.batch_folder_var, width=65).grid(
            row=1, column=1, padx=5, pady=5
        )
        ttk.Button(input_frame, text="찾아보기", command=self.browse_batch_folder).grid(
            row=1, column=2, padx=5, pady=5
        )
        
        # === 옵션 섹션 ===
        options_frame = ttk.LabelFrame(main_frame, text="처리 옵션", padding="10")
        options_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 체크박스 옵션
        self.create_rgb_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame, 
            text="RGB 합성 이미지 생성",
            variable=self.create_rgb_var
        ).grid(row=0, column=0, sticky=tk.W, padx=5)
        
        self.create_ndvi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="NDVI 계산 및 분석 리포트(HTML) 생성",
            variable=self.create_ndvi_var
        ).grid(row=0, column=1, sticky=tk.W, padx=5)
        
        self.open_qgis_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="완료 후 QGIS 프로젝트 열기",
            variable=self.open_qgis_var
        ).grid(row=0, column=2, sticky=tk.W, padx=5)

        # 모자이크 옵션
        self.mosaic_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="여러 장면(Scene) 모자이크 처리 후 합성",
            variable=self.mosaic_var
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, padx=5, pady=(8,0))

        # QGIS 실행 파일 경로
        ttk.Label(options_frame, text="QGIS 실행 파일:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=(8,0))
        ttk.Entry(options_frame, textvariable=self.qgis_path_var, width=65).grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=(8,0))
        ttk.Button(options_frame, text="찾아보기", command=self.browse_qgis_exe).grid(row=2, column=2, padx=5, pady=(8,0))
        
        # === 실행 버튼 ===
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=10)
        
        self.process_button = ttk.Button(
            button_frame,
            text="처리 시작",
            command=self.start_processing,
            width=20
        )
        self.process_button.grid(row=0, column=0, padx=5)
        
        self.stop_button = ttk.Button(
            button_frame,
            text="중지",
            command=self.stop_processing,
            state=tk.DISABLED,
            width=20
        )
        self.stop_button.grid(row=0, column=1, padx=5)
        
        ttk.Button(
            button_frame,
            text="출력 폴더 열기",
            command=self.open_output_folder,
            width=20
        ).grid(row=0, column=2, padx=5)
        
        # === 진행 상태 ===
        progress_frame = ttk.LabelFrame(main_frame, text="진행 상태", padding="10")
        progress_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        
        self.status_label = ttk.Label(progress_frame, text="대기 중...", foreground="#2980b9")
        self.status_label.grid(row=1, column=0, sticky=tk.W)
        
        # === 로그 출력 ===
        log_frame = ttk.LabelFrame(main_frame, text="처리 로그", padding="10")
        log_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            width=100,
            height=18,
            wrap=tk.WORD,
            font=("Consolas", 9)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.log_text.tag_config("success", foreground="#27ae60")
        self.log_text.tag_config("error", foreground="#c0392b")
        self.log_text.tag_config("warning", foreground="#d35400")
        self.log_text.tag_config("info", foreground="#2980b9")
        
        # 하단 정보
        info_frame = ttk.Frame(main_frame)
        info_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E))
        
        ttk.Label(
            info_frame,
            text="v2.0.1 | CAS500-1 L3A Processor | Compatible with QGIS / Standalone Python",
            font=("맑은 고딕", 8)
        ).grid(row=0, column=0, sticky=tk.W)
        
        # 그리드 가중치
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)
        progress_frame.columnconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # 초기 상태 점검
        self.log("국토정보위성 자동 처리 시스템이 준비되었습니다.", "info")
        if not GDAL_AVAILABLE:
            self.log("[ERROR] GDAL 라이브러리를 찾을 수 없습니다.", "error")
            self.log(f"원인: {GDAL_ERROR}", "error")
            self.log("QGIS 환경 또는 run.bat를 통해 실행해주세요.", "warning")
            self.process_button.config(state=tk.DISABLED)
        else:
            self.log("[OK] GDAL 및 NumPy 연동 확인 완료", "success")
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def process_queue(self):
        """백그라운드 스레드에서 전달된 메시지를 메인 UI 스레드에서 안전하게 처리"""
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "LOG":
                    message, level = data
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", level)
                    self.log_text.see(tk.END)
                elif msg_type == "STATUS":
                    message, progress = data
                    self.status_label.config(text=message)
                    if progress is not None:
                        self.progress_var.set(progress)
                elif msg_type == "COMPLETE":
                    self.is_processing = False
                    self.process_button.config(state=tk.NORMAL)
                    self.stop_button.config(state=tk.DISABLED)
                    self.status_label.config(text="처리 완료")
                    total, success, failed, first_folder = data
                    messagebox.showinfo(
                        "완료",
                        f"처리가 완료되었습니다!\n\n"
                        f"전체 데이터셋: {total}개\n"
                        f"성공: {success}개\n"
                        f"실패: {failed}개"
                    )
                    if self.open_qgis_var.get() and success > 0 and first_folder:
                        self.open_qgis_project(first_folder)
                elif msg_type == "ERROR_POPUP":
                    self.is_processing = False
                    self.process_button.config(state=tk.NORMAL)
                    self.stop_button.config(state=tk.DISABLED)
                    messagebox.showerror("오류", str(data))
                self.msg_queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def log(self, message, level="info"):
        """스레드 안전 로그 큐 전송"""
        self.msg_queue.put(("LOG", (message, level)))

    def update_status(self, message, progress=None):
        """스레드 안전 상태 큐 전송"""
        self.msg_queue.put(("STATUS", (message, progress)))

    def on_closing(self):
        try:
            self.save_settings()
        finally:
            self.root.destroy()

    def load_settings(self):
        cfg = configparser.ConfigParser()
        if os.path.exists(self.settings_path):
            try:
                cfg.read(self.settings_path, encoding='utf-8')
                q = cfg.get('qgis', 'exe_path', fallback='')
                if q:
                    self.qgis_path_var.set(q)
            except Exception:
                pass

    def save_settings(self):
        try:
            cfg = configparser.ConfigParser()
            cfg['qgis'] = {
                'exe_path': self.qgis_path_var.get().strip()
            }
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                cfg.write(f)
        except Exception:
            pass

    def browse_qgis_exe(self):
        path = filedialog.askopenfilename(
            title="QGIS 실행 파일 선택",
            filetypes=[
                ("QGIS 실행 파일", "qgis*.exe"),
                ("배치 파일", "qgis*.bat"),
                ("모든 파일", "*.*")
            ]
        )
        if path:
            self.qgis_path_var.set(path)
            self.save_settings()
        
    def browse_single_folder(self):
        folder = filedialog.askdirectory(title="처리할 폴더 선택 (*_Aux.xml 포함)")
        if folder:
            self.single_folder_var.set(folder)
            self.log(f"단일 폴더 선택: {folder}", "info")
            
    def browse_batch_folder(self):
        folder = filedialog.askdirectory(title="여러 대상 폴더가 있는 루트 폴더 선택")
        if folder:
            self.batch_folder_var.set(folder)
            found_folders = self.find_kompsat_folders(folder)
            self.log(f"배치 루트 폴더 선택: {folder}", "info")
            self.log(f"발견된 대상 폴더: {len(found_folders)}개", "info")
            for f in found_folders:
                self.log(f"  * {os.path.basename(f)}", "info")
    
    def find_kompsat_folders(self, root_dir):
        folders = []
        try:
            if any(fn.lower().endswith('_aux.xml') for fn in os.listdir(root_dir)):
                folders.append(root_dir)
            for item in os.listdir(root_dir):
                item_path = os.path.join(root_dir, item)
                if not os.path.isdir(item_path):
                    continue
                try:
                    if any(fn.lower().endswith('_aux.xml') for fn in os.listdir(item_path)):
                        folders.append(item_path)
                except Exception:
                    continue
        except Exception as e:
            self.log(f"폴더 검색 오류: {str(e)}", "error")
        return sorted(list(set(folders)))
        
    def start_processing(self):
        if self.is_processing:
            return
        
        if not GDAL_AVAILABLE:
            messagebox.showerror("오류", "GDAL 라이브러리를 사용할 수 없습니다.")
            return
        
        single_folder = self.single_folder_var.get().strip()
        batch_folder = self.batch_folder_var.get().strip()
        
        if not single_folder and not batch_folder:
            messagebox.showwarning("경고", "처리할 폴더를 선택해주세요.")
            return
        
        folders = []
        if single_folder:
            if not os.path.isdir(single_folder):
                messagebox.showerror("오류", f"폴더를 찾을 수 없습니다:\n{single_folder}")
                return
            folders.append(single_folder)
        
        if batch_folder:
            found = self.find_kompsat_folders(batch_folder)
            if not found:
                messagebox.showwarning("경고", f"대상 폴더(*_Aux.xml)를 찾을 수 없습니다:\n{batch_folder}")
                return
            folders.extend(found)
        
        folders = list(dict.fromkeys(folders))
        if not folders:
            messagebox.showwarning("경고", "처리할 대상 폴더가 없습니다.")
            return
        
        if len(folders) > 1:
            response = messagebox.askyesno(
                "확인",
                f"{len(folders)}개의 폴더를 일괄 처리하시겠습니까?\n\n" +
                "\n".join([f"• {os.path.basename(f)}" for f in folders[:5]]) +
                (f"\n... 외 {len(folders)-5}개" if len(folders) > 5 else "")
            )
            if not response:
                return
        
        self.is_processing = True
        self.process_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        
        threading.Thread(target=self.process_folders_worker, args=(folders,), daemon=True).start()
        
    def process_folders_worker(self, folders):
        """백그라운드 작업 스레드"""
        try:
            self.log("=" * 70, "info")
            self.log("위성 데이터 자동 처리 시작", "info")
            self.log("=" * 70, "info")
            
            total_folders = len(folders)
            mosaic_bands = { 'Red': [], 'Green': [], 'Blue': [], 'NIR': [] }
            datasets_total = 0
            success_count = 0
            failed_count = 0
            
            for i, folder in enumerate(folders, 1):
                if not self.is_processing:
                    self.log("사용자에 의해 처리가 중지되었습니다.", "warning")
                    break
                
                folder_name = os.path.basename(folder)
                self.log(f"\n[{i}/{total_folders}] 폴더: {folder_name}", "info")
                self.update_status(f"처리 중: {folder_name}", (i-1) / total_folders * 100)
                
                try:
                    xml_list = [
                        os.path.join(folder, f)
                        for f in os.listdir(folder)
                        if f.lower().endswith('_aux.xml')
                    ]
                    xml_list.sort()

                    if not xml_list:
                        raise Exception("*_Aux.xml 메타데이터 파일을 찾을 수 없습니다.")

                    datasets_total += len(xml_list)

                    for j, xml_path in enumerate(xml_list, 1):
                        if not self.is_processing:
                            break
                        ds_name = os.path.basename(xml_path)
                        self.log(f"  * 데이터셋 {j}/{len(xml_list)}: {ds_name}", "info")

                        processor = KompsatProcessor(folder)
                        processor.xml_file = xml_path

                        self.log("    - XML 메타데이터 파싱...", "info")
                        if not processor.parse_metadata():
                            raise Exception("메타데이터 파싱 실패")

                        self.log("    - GCP 기반 지리보정(EPSG:5179)...", "info")
                        if not processor.georeference_bands():
                            raise Exception("지리보정 실패")

                        for bname, fpath in processor.georef_files.items():
                            if bname in mosaic_bands and os.path.exists(fpath):
                                mosaic_bands[bname].append(fpath)

                        if self.create_rgb_var.get():
                            self.log("    - RGB 합성 이미지 생성...", "info")
                            processor.create_rgb_composite()

                        if self.create_ndvi_var.get():
                            self.log("    - NDVI 계산 및 분석 리포트 생성...", "info")
                            ndvi_f = processor.calculate_ndvi()
                            if ndvi_f:
                                KompsatProcessor.generate_ndvi_html_report(ndvi_f)

                        self.log("    [OK] 해당 데이터셋 완료", "success")
                        success_count += 1
                    
                except Exception as e:
                    self.log(f"  [ERROR] {str(e)}", "error")
                    failed_count += 1
            
            # 모자이크 처리
            if self.mosaic_var.get() and self.is_processing:
                try:
                    self.log("\n모자이크 결합 처리 시작...", "info")
                    if len(folders) == 1:
                        mosaic_out = os.path.join(folders[0], "ProcessedOutputs", "Mosaic")
                    else:
                        base_dir = os.path.dirname(folders[0])
                        mosaic_out = os.path.join(base_dir, "ProcessedOutputs_Mosaic")
                    os.makedirs(mosaic_out, exist_ok=True)

                    red_mos = green_mos = blue_mos = nir_mos = None
                    if mosaic_bands['Red']:
                        self.log(f"  * Red 모자이크 ({len(mosaic_bands['Red'])}장)...", "info")
                        red_mos = KompsatProcessor.mosaic_raster(mosaic_bands['Red'], os.path.join(mosaic_out, 'Mosaic_Red.tif'))
                    if mosaic_bands['Green']:
                        self.log(f"  * Green 모자이크 ({len(mosaic_bands['Green'])}장)...", "info")
                        green_mos = KompsatProcessor.mosaic_raster(mosaic_bands['Green'], os.path.join(mosaic_out, 'Mosaic_Green.tif'))
                    if mosaic_bands['Blue']:
                        self.log(f"  * Blue 모자이크 ({len(mosaic_bands['Blue'])}장)...", "info")
                        blue_mos = KompsatProcessor.mosaic_raster(mosaic_bands['Blue'], os.path.join(mosaic_out, 'Mosaic_Blue.tif'))
                    if mosaic_bands['NIR']:
                        self.log(f"  * NIR 모자이크 ({len(mosaic_bands['NIR'])}장)...", "info")
                        nir_mos = KompsatProcessor.mosaic_raster(mosaic_bands['NIR'], os.path.join(mosaic_out, 'Mosaic_NIR.tif'))

                    if red_mos and green_mos and blue_mos and self.create_rgb_var.get():
                        self.log("  * 모자이크 RGB 합성 생성...", "info")
                        KompsatProcessor.create_rgb_from_singlebands(red_mos, green_mos, blue_mos, os.path.join(mosaic_out, 'Mosaic_RGB.tif'))

                    if red_mos and nir_mos and self.create_ndvi_var.get():
                        self.log("  * 모자이크 NDVI 계산...", "info")
                        ndvi_mos = KompsatProcessor.compute_ndvi_from_files(red_mos, nir_mos, os.path.join(mosaic_out, 'Mosaic_NDVI.tif'))
                        if ndvi_mos:
                            KompsatProcessor.generate_ndvi_html_report(ndvi_mos)

                    self.log(f"[OK] 모자이크 저장 완료: {mosaic_out}", "success")
                except Exception as me:
                    self.log(f"[ERROR] 모자이크 실패: {str(me)}", "error")

            summary_total = datasets_total if datasets_total else total_folders
            self.log("\n" + "=" * 70, "info")
            self.log(f"처리 종료 | 총 {summary_total}개 중 {success_count}개 성공, {failed_count}개 실패", "success" if failed_count == 0 else "warning")
            self.log("=" * 70, "info")

            first_f = folders[0] if folders else None
            self.msg_queue.put(("COMPLETE", (summary_total, success_count, failed_count, first_f)))

        except Exception as e:
            self.log(f"[FATAL] 치명적 오류: {str(e)}", "error")
            self.msg_queue.put(("ERROR_POPUP", str(e)))

    def stop_processing(self):
        if self.is_processing:
            if messagebox.askyesno("확인", "처리를 중지하시겠습니까?"):
                self.is_processing = False
                self.log("중지 신호 전송됨...", "warning")
    
    def open_output_folder(self):
        single_folder = self.single_folder_var.get().strip()
        batch_folder = self.batch_folder_var.get().strip()
        folder = single_folder if single_folder else batch_folder
        
        if folder and os.path.isdir(folder):
            output_dir = os.path.join(folder, "ProcessedOutputs")
            if os.path.isdir(output_dir):
                os.startfile(output_dir)
            else:
                messagebox.showinfo("안내", "아직 출력 폴더가 생성되지 않았습니다.\n처리를 먼저 실행해주세요.")
        else:
            messagebox.showwarning("경고", "폴더를 먼저 선택해주세요.")
    
    def find_qgis_executable(self):
        """Windows에서 QGIS 실행 파일 위치 탐색"""
        user_path = self.qgis_path_var.get().strip()
        if user_path and os.path.exists(user_path):
            return user_path
        
        qgis_in_path = shutil.which('qgis')
        if qgis_in_path:
            return qgis_in_path
        
        candidates = []
        pf = os.environ.get('ProgramFiles', r'C:\Program Files')
        pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
        for base in [pf, pf86, r"C:\OSGeo4W", r"C:\OSGeo4W64"]:
            if not os.path.isdir(base):
                continue
            for pattern in ['QGIS*', 'bin']:
                candidates.extend(glob.glob(os.path.join(base, pattern, 'bin', 'qgis-bin.exe')))
                candidates.extend(glob.glob(os.path.join(base, pattern, 'bin', 'qgis.exe')))
                candidates.extend(glob.glob(os.path.join(base, pattern, 'bin', 'qgis*.bat')))
                candidates.extend(glob.glob(os.path.join(base, 'bin', 'qgis-bin.exe')))
                candidates.extend(glob.glob(os.path.join(base, 'bin', 'qgis.exe')))
        
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def open_qgis_project(self, folder):
        try:
            processed_dir = os.path.join(folder, "ProcessedOutputs")
            layers = []
            
            # 모자이크 우선, 없으면 개별 결과
            mosaic_dir = os.path.join(processed_dir, 'Mosaic')
            for name in ['Mosaic_NDVI.tif', 'Mosaic_RGB.tif']:
                p = os.path.join(mosaic_dir, name)
                if os.path.exists(p):
                    layers.append(p)
            
            if not layers:
                for f in os.listdir(processed_dir):
                    if f.startswith('NDVI_') and f.endswith('.tif'):
                        layers.append(os.path.join(processed_dir, f))
                        break

            if not layers:
                return

            exe = self.find_qgis_executable()
            if exe:
                if exe.lower().endswith('.bat'):
                    subprocess.Popen([exe] + layers, shell=True)
                else:
                    subprocess.Popen([exe] + layers)
                return
            
            os.startfile(layers[0])
        except Exception as e:
            self.log(f"QGIS 열기 실패: {str(e)}", "error")

def main():
    root = tk.Tk()
    app = KompsatGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
