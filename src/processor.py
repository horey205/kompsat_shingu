#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국토정보위성 자동 처리 모듈
KOMPSAT L3A 데이터 지리보정 및 NDVI 계산 자동화
"""

import xml.etree.ElementTree as ET
import os
import sys
import numpy as np
from datetime import datetime

# GDAL import check
try:
    from osgeo import gdal, osr
    gdal.UseExceptions()
except ImportError:
    print("[ERROR] GDAL library not found. Please install GDAL or run via QGIS environment.")
    sys.exit(1)

class KompsatProcessor:
    """KOMPSAT 위성 데이터 자동 처리 클래스"""
    
    def __init__(self, input_dir):
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.join(self.input_dir, 'ProcessedOutputs')
        self.xml_file = None
        self.bands_info = {}
        self.georef_files = {}
        
        # 출력 디렉토리 생성
        os.makedirs(self.output_dir, exist_ok=True)
        
    def find_xml_file(self):
        """Aux.xml 파일 하나 찾기 (레거시 호환)"""
        try:
            for filename in os.listdir(self.input_dir):
                if filename.lower().endswith('_aux.xml'):
                    self.xml_file = os.path.join(self.input_dir, filename)
                    return True
        except Exception:
            pass
        return False

    def find_xml_files(self):
        """폴더 내 모든 Aux.xml 리스트 반환"""
        xmls = []
        try:
            for filename in os.listdir(self.input_dir):
                if filename.lower().endswith('_aux.xml'):
                    xmls.append(os.path.join(self.input_dir, filename))
        except Exception:
            pass
        return sorted(xmls)
    
    def extract_band_info(self, root, band_tag, band_name):
        """XML에서 특정 밴드의 정보 추출"""
        band_elem = root.find(f'.//Image/{band_tag}')
        if band_elem is None:
            return None
        
        info = {
            'filename': band_elem.find('ImageFileName').text,
            'width': int(band_elem.find('.//ImageSize/Width').text),
            'height': int(band_elem.find('.//ImageSize/Height').text),
            'band_name': band_name
        }
        
        # 4개 코너 좌표 추출
        coords = band_elem.find('ImagingCoordinates')
        info['ul'] = (float(coords.find('.//UpperLeft/Longitude').text), 
                      float(coords.find('.//UpperLeft/Latitude').text))
        info['ur'] = (float(coords.find('.//UpperRight/Longitude').text), 
                      float(coords.find('.//UpperRight/Latitude').text))
        info['ll'] = (float(coords.find('.//LowerLeft/Longitude').text), 
                      float(coords.find('.//LowerLeft/Latitude').text))
        info['lr'] = (float(coords.find('.//LowerRight/Longitude').text), 
                      float(coords.find('.//LowerRight/Latitude').text))
        
        return info
    
    def parse_metadata(self):
        """XML 메타데이터 파싱"""
        print("\n" + "=" * 70)
        print("[*] 1단계: XML 메타데이터 파싱")
        print("=" * 70)

        # self.xml_file이 미리 지정되지 않았다면 첫 번째 파일을 탐색
        if not self.xml_file:
            if not self.find_xml_file():
                print("[ERROR] Aux.xml 파일을 찾을 수 없습니다.")
                return False

        print(f"[OK] XML 파일 발견: {os.path.basename(self.xml_file)}")
        
        try:
            tree = ET.parse(self.xml_file)
            root = tree.getroot()
        except Exception as e:
            print(f"[ERROR] XML 파싱 실패: {str(e)}")
            return False
        
        # 4개 밴드 정보 추출 (매 실행마다 초기화)
        self.bands_info = {
            'Blue': self.extract_band_info(root, 'SR1', 'Blue'),
            'Green': self.extract_band_info(root, 'SR2', 'Green'),
            'Red': self.extract_band_info(root, 'SR3', 'Red'),
            'NIR': self.extract_band_info(root, 'SR4', 'NIR')
        }
        
        # 정보 출력
        for name, info in self.bands_info.items():
            if info:
                print(f"  {name:6s} 밴드: {info['filename']} ({info['width']}x{info['height']})")
        
        return True
    
    def georeference_image(self, input_file, output_file, info):
        """GCP를 사용해서 이미지 지리보정"""
        if not os.path.exists(input_file):
            print(f"[ERROR] 입력 파일 없음: {input_file}")
            return False

        # GCP 생성 (픽셀 좌표, 지리 좌표)
        gcps = [
            gdal.GCP(info['ul'][0], info['ul'][1], 0, 0, 0),
            gdal.GCP(info['ur'][0], info['ur'][1], 0, info['width'], 0),
            gdal.GCP(info['ll'][0], info['ll'][1], 0, 0, info['height']),
            gdal.GCP(info['lr'][0], info['lr'][1], 0, info['width'], info['height'])
        ]
        
        src_ds = gdal.Open(input_file)
        if src_ds is None:
            return False
        
        temp_vrt = output_file.replace('.tif', '_temp.vrt')
        
        try:
            translate_options = gdal.TranslateOptions(
                format='VRT',
                outputSRS='EPSG:4326'
            )
            temp_ds = gdal.Translate(temp_vrt, src_ds, options=translate_options)
            
            srs_wgs84 = osr.SpatialReference()
            srs_wgs84.ImportFromEPSG(4326)
            temp_ds.SetGCPs(gcps, srs_wgs84.ExportToWkt())
            temp_ds = None
            
            warp_options = gdal.WarpOptions(
                format='GTiff',
                srcSRS='EPSG:4326',
                dstSRS='EPSG:5179',  # Korea2000 좌표계
                resampleAlg='cubic',
                creationOptions=['COMPRESS=LZW', 'TILED=YES']
            )
            
            warp_ds = gdal.Warp(output_file, temp_vrt, options=warp_options)
            warp_ds = None
            return True
        except Exception as e:
            print(f"[ERROR] 지리보정 오류: {str(e)}")
            return False
        finally:
            src_ds = None
            if os.path.exists(temp_vrt):
                try:
                    os.remove(temp_vrt)
                except Exception:
                    pass
    
    def georeference_bands(self):
        """모든 밴드 지리보정"""
        print("\n" + "=" * 70)
        print("[*] 2단계: 지리보정 (GCP 기반 EPSG:5179)")
        print("=" * 70)
        
        for band_name, info in self.bands_info.items():
            if info is None:
                continue
            
            input_path = os.path.join(self.input_dir, info['filename'])
            output_filename = info['filename'].replace('.tif', '_georef.tif')
            output_path = os.path.join(self.output_dir, output_filename)
            
            print(f"  처리 중: {band_name:5s} 밴드... ", end='', flush=True)
            
            if self.georeference_image(input_path, output_path, info):
                self.georef_files[band_name] = output_path
                print("[OK]")
            else:
                print("[FAILED]")
        
        success_count = len(self.georef_files)
        print(f"\n[OK] 지리보정 완료: {success_count}/4 개 밴드")
        return success_count == 4
    
    def create_rgb_composite(self):
        """RGB 합성 이미지 생성"""
        print("\n" + "=" * 70)
        print("[*] 3단계: RGB 합성 이미지 생성")
        print("=" * 70)
        
        if 'Red' not in self.georef_files or 'Green' not in self.georef_files or 'Blue' not in self.georef_files:
            print("[ERROR] RGB 밴드가 부족합니다.")
            return None
        
        base_name = os.path.basename(self.xml_file).replace('_Aux.xml', '').replace('_aux.xml', '')
        parts = base_name.split('_')
        date_str = parts[2] if len(parts) > 2 else "Output"
        rgb_file = os.path.join(self.output_dir, f'RGB_Composite_{base_name}.tif')
        
        red_ds = gdal.Open(self.georef_files['Red'])
        green_ds = gdal.Open(self.georef_files['Green'])
        blue_ds = gdal.Open(self.georef_files['Blue'])
        
        # 크기 정합성 검증
        x_size = red_ds.RasterXSize
        y_size = red_ds.RasterYSize
        if (green_ds.RasterXSize != x_size or green_ds.RasterYSize != y_size or
            blue_ds.RasterXSize != x_size or blue_ds.RasterYSize != y_size):
            print("[WARN] 밴드 간 해상도/크기 불일치 감지. Red 밴드 기준으로 재정렬합니다.")
            green_ds = None
            blue_ds = None
            
            # Warp로 일치화
            aligned_g = self.georef_files['Green'].replace('.tif', '_align.tif')
            aligned_b = self.georef_files['Blue'].replace('.tif', '_align.tif')
            gdal.Warp(aligned_g, self.georef_files['Green'], width=x_size, height=y_size)
            gdal.Warp(aligned_b, self.georef_files['Blue'], width=x_size, height=y_size)
            green_ds = gdal.Open(aligned_g)
            blue_ds = gdal.Open(aligned_b)

        red_data = red_ds.GetRasterBand(1).ReadAsArray()
        green_data = green_ds.GetRasterBand(1).ReadAsArray()
        blue_data = blue_ds.GetRasterBand(1).ReadAsArray()
        
        driver = gdal.GetDriverByName('GTiff')
        rgb_ds = driver.Create(
            rgb_file,
            x_size,
            y_size,
            3,
            gdal.GDT_UInt16,
            options=['COMPRESS=LZW', 'TILED=YES', 'PHOTOMETRIC=RGB']
        )
        
        rgb_ds.SetGeoTransform(red_ds.GetGeoTransform())
        rgb_ds.SetProjection(red_ds.GetProjection())
        
        rgb_ds.GetRasterBand(1).WriteArray(red_data)
        rgb_ds.GetRasterBand(2).WriteArray(green_data)
        rgb_ds.GetRasterBand(3).WriteArray(blue_data)
        
        for i in range(1, 4):
            rgb_ds.GetRasterBand(i).ComputeStatistics(False)
        
        red_ds = None
        green_ds = None
        blue_ds = None
        rgb_ds = None
        
        print(f"[OK] RGB 합성 완료: {os.path.basename(rgb_file)}")
        return rgb_file
    
    def calculate_ndvi(self):
        """NDVI 계산 및 안전한 NoData 마스킹"""
        print("\n" + "=" * 70)
        print("[*] 4단계: NDVI 계산")
        print("=" * 70)
        
        if 'Red' not in self.georef_files or 'NIR' not in self.georef_files:
            print("[ERROR] Red 또는 NIR 밴드가 없습니다.")
            return None
        
        base_name = os.path.basename(self.xml_file).replace('_Aux.xml', '').replace('_aux.xml', '')
        ndvi_file = os.path.join(self.output_dir, f'NDVI_{base_name}.tif')
        
        red_ds = gdal.Open(self.georef_files['Red'])
        nir_ds = gdal.Open(self.georef_files['NIR'])
        
        # 크기 정합성 확인
        x_size = red_ds.RasterXSize
        y_size = red_ds.RasterYSize
        if nir_ds.RasterXSize != x_size or nir_ds.RasterYSize != y_size:
            nir_ds = None
            aligned_nir = self.georef_files['NIR'].replace('.tif', '_align.tif')
            gdal.Warp(aligned_nir, self.georef_files['NIR'], width=x_size, height=y_size)
            nir_ds = gdal.Open(aligned_nir)

        red_data = red_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
        nir_data = nir_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
        
        # 유효 마스크: 배경(0, 0) 및 무효 영역 제외
        valid_mask = (nir_data > 0) | (red_data > 0)
        denominator = nir_data + red_data
        
        # 0 나누기 경고 방지 및 계산
        with np.errstate(divide='ignore', invalid='ignore'):
            ndvi = (nir_data - red_data) / denominator
            # 무효 픽셀 및 NaN을 NoDataValue(-9999.0)로 완벽히 치환
            ndvi = np.where(valid_mask & (denominator > 0), ndvi, -9999.0)
            ndvi = np.nan_to_num(ndvi, nan=-9999.0)
        
        # 유효 데이터 통계
        valid_pixels = ndvi[ndvi != -9999.0]
        if len(valid_pixels) > 0:
            ndvi_min = float(np.min(valid_pixels))
            ndvi_max = float(np.max(valid_pixels))
            ndvi_mean = float(np.mean(valid_pixels))
            print(f"  NDVI 범위: {ndvi_min:.4f} ~ {ndvi_max:.4f}")
            print(f"  NDVI 평균: {ndvi_mean:.4f}")
        else:
            print("  [WARN] 유효한 픽셀이 없습니다.")
        
        # NDVI 저장
        driver = gdal.GetDriverByName('GTiff')
        ndvi_ds = driver.Create(
            ndvi_file,
            x_size,
            y_size,
            1,
            gdal.GDT_Float32,
            options=['COMPRESS=LZW', 'TILED=YES']
        )
        
        ndvi_ds.SetGeoTransform(red_ds.GetGeoTransform())
        ndvi_ds.SetProjection(red_ds.GetProjection())
        
        ndvi_band = ndvi_ds.GetRasterBand(1)
        ndvi_band.WriteArray(ndvi)
        ndvi_band.SetNoDataValue(-9999.0)
        ndvi_band.ComputeStatistics(False)
        
        red_ds = None
        nir_ds = None
        ndvi_ds = None
        
        print(f"[OK] NDVI 계산 완료: {os.path.basename(ndvi_file)}")
        return ndvi_file

    # ===== 모자이크/외부 파일 기반 유틸 =====
    @staticmethod
    def mosaic_raster(input_files, output_file, dst_srs='EPSG:5179', resampleAlg='cubic'):
        """여러 래스터를 하나로 모자이크 (GTiff)"""
        if not input_files:
            return None
        warp_opts = gdal.WarpOptions(
            format='GTiff',
            dstSRS=dst_srs,
            resampleAlg=resampleAlg,
            creationOptions=['COMPRESS=LZW', 'TILED=YES']
        )
        ds = gdal.Warp(output_file, input_files, options=warp_opts)
        ds = None
        return output_file if os.path.exists(output_file) else None

    @staticmethod
    def create_rgb_from_singlebands(red_file, green_file, blue_file, output_file):
        """단일밴드 파일 3개로 RGB 합성 생성"""
        if not (red_file and green_file and blue_file):
            return None
        red_ds = gdal.Open(red_file)
        green_ds = gdal.Open(green_file)
        blue_ds = gdal.Open(blue_file)
        if not red_ds or not green_ds or not blue_ds:
            return None

        red = red_ds.GetRasterBand(1).ReadAsArray()
        green = green_ds.GetRasterBand(1).ReadAsArray()
        blue = blue_ds.GetRasterBand(1).ReadAsArray()

        driver = gdal.GetDriverByName('GTiff')
        rgb_ds = driver.Create(
            output_file,
            red_ds.RasterXSize,
            red_ds.RasterYSize,
            3,
            gdal.GDT_UInt16,
            options=['COMPRESS=LZW', 'TILED=YES', 'PHOTOMETRIC=RGB']
        )
        rgb_ds.SetGeoTransform(red_ds.GetGeoTransform())
        rgb_ds.SetProjection(red_ds.GetProjection())
        rgb_ds.GetRasterBand(1).WriteArray(red)
        rgb_ds.GetRasterBand(2).WriteArray(green)
        rgb_ds.GetRasterBand(3).WriteArray(blue)
        for i in range(1, 4):
            rgb_ds.GetRasterBand(i).ComputeStatistics(False)
        red_ds = green_ds = blue_ds = None
        rgb_ds = None
        return output_file if os.path.exists(output_file) else None

    @staticmethod
    def compute_ndvi_from_files(red_file, nir_file, output_file):
        """Red/NIR 파일로 NDVI 계산 후 저장"""
        if not (red_file and nir_file):
            return None
        red_ds = gdal.Open(red_file)
        nir_ds = gdal.Open(nir_file)
        if not red_ds or not nir_ds:
            return None
        red = red_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
        nir = nir_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
        
        valid_mask = (nir > 0) | (red > 0)
        denom = nir + red
        with np.errstate(divide='ignore', invalid='ignore'):
            ndvi = (nir - red) / denom
            ndvi = np.where(valid_mask & (denom > 0), ndvi, -9999.0)
            ndvi = np.nan_to_num(ndvi, nan=-9999.0)

        driver = gdal.GetDriverByName('GTiff')
        ndvi_ds = driver.Create(
            output_file,
            red_ds.RasterXSize,
            red_ds.RasterYSize,
            1,
            gdal.GDT_Float32,
            options=['COMPRESS=LZW', 'TILED=YES']
        )
        ndvi_ds.SetGeoTransform(red_ds.GetGeoTransform())
        ndvi_ds.SetProjection(red_ds.GetProjection())
        band = ndvi_ds.GetRasterBand(1)
        band.WriteArray(ndvi)
        band.SetNoDataValue(-9999.0)
        band.ComputeStatistics(False)
        red_ds = nir_ds = None
        ndvi_ds = None
        return output_file if os.path.exists(output_file) else None
    
    def generate_report(self, rgb_file, ndvi_file):
        """처리 결과 보고서 콘솔 출력"""
        print("\n" + "=" * 70)
        print(" [OK] 처리 완료 보고서")
        print("=" * 70)
        print(f"처리 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"입력 폴더: {os.path.basename(self.input_dir)}")
        print(f"출력 폴더: {self.output_dir}")
        print("\n생성된 파일:")
        print("-" * 70)
        
        file_count = 0
        for band_name, filepath in self.georef_files.items():
            if os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                print(f"  * {band_name:5s} 밴드 (지리보정): {size_mb:.2f} MB")
                file_count += 1
        
        if rgb_file and os.path.exists(rgb_file):
            size_mb = os.path.getsize(rgb_file) / (1024 * 1024)
            print(f"  * RGB 합성 이미지: {size_mb:.2f} MB")
            file_count += 1
        
        if ndvi_file and os.path.exists(ndvi_file):
            size_mb = os.path.getsize(ndvi_file) / (1024 * 1024)
            print(f"  * NDVI 분석 결과: {size_mb:.2f} MB")
            file_count += 1
        
        print(f"\n[OK] 총 {file_count}개 파일 생성 완료")
        print("=" * 70)
    
    # ========= NDVI 리포트(HTML) 유틸 =========
    @staticmethod
    def _compute_band_statistics(tif_path):
        ds = gdal.Open(tif_path)
        if ds is None:
            return None
        band = ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        arr = band.ReadAsArray()
        ds = None
        
        if nodata is not None:
            valid_arr = arr[arr != nodata]
        else:
            valid_arr = arr[~np.isnan(arr)]

        if len(valid_arr) == 0:
            return None

        minv = float(np.min(valid_arr))
        maxv = float(np.max(valid_arr))
        meanv = float(np.mean(valid_arr))
        stdv = float(np.std(valid_arr))
        hist, bin_edges = np.histogram(valid_arr, bins=256, range=(minv, maxv))
        
        return {
            'min': minv,
            'max': maxv,
            'mean': meanv,
            'std': stdv,
            'hist': hist.tolist(),
        }

    @staticmethod
    def _export_quicklook_png(tif_path, out_png, width_max=1024):
        ds = gdal.Open(tif_path)
        if ds is None:
            return False
        xsize = ds.RasterXSize
        ysize = ds.RasterYSize
        ratio = min(1.0, float(width_max) / float(xsize))
        w = max(1, int(xsize * ratio))
        h = max(1, int(ysize * ratio))
        band = ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        arr = band.ReadAsArray()
        ds = None
        
        if nodata is not None:
            valid_arr = arr[arr != nodata]
        else:
            valid_arr = arr[~np.isnan(arr)]
            
        minv = float(np.min(valid_arr)) if len(valid_arr) > 0 else -1.0
        maxv = float(np.max(valid_arr)) if len(valid_arr) > 0 else 1.0

        ds_again = gdal.Open(tif_path)
        opts = gdal.TranslateOptions(
            format='PNG',
            outputType=gdal.GDT_Byte,
            width=w,
            height=h,
            scaleParams=[[minv, maxv, 1, 255]],
            noData=0
        )
        res_ds = gdal.Translate(out_png, ds_again, options=opts)
        res_ds = None
        ds_again = None
        return os.path.exists(out_png)

    @staticmethod
    def _percentiles_from_hist(hist, minv, maxv, percentiles=(5, 25, 50, 75, 95)):
        if not hist:
            return {}
        total = float(sum(hist))
        if total == 0:
            return {}
        edges = np.linspace(minv, maxv, num=len(hist)+1)
        csum = np.cumsum(hist) / total
        results = {}
        for p in percentiles:
            t = p / 100.0
            idx = np.searchsorted(csum, t)
            idx = min(max(idx, 0), len(edges)-2)
            results[p] = float(edges[idx])
        return results

    @staticmethod
    def generate_ndvi_html_report(ndvi_path, rgb_path=None, title="NDVI 결과 보고서"):
        try:
            if not os.path.exists(ndvi_path):
                return None
            out_dir = os.path.dirname(ndvi_path)
            base_name = os.path.splitext(os.path.basename(ndvi_path))[0]
            html_path = os.path.join(out_dir, f"{base_name}_Report.html")

            stats = KompsatProcessor._compute_band_statistics(ndvi_path)
            if not stats:
                return None
            ptiles = KompsatProcessor._percentiles_from_hist(stats['hist'], stats['min'], stats['max'])

            classes = [
                ("< 0.0 (수계/비식생)", -1.0, 0.0),
                ("0.0 - 0.2 (나지/건물)", 0.0, 0.2),
                ("0.2 - 0.4 (희박 식생)", 0.2, 0.4),
                ("0.4 - 0.6 (보통 식생)", 0.4, 0.6),
                ("0.6 - 0.8 (밀집 식생)", 0.6, 0.8),
                (" > 0.8 (매우 울창)", 0.8, 2.0),
            ]
            
            hist = stats['hist']
            edges = np.linspace(stats['min'], stats['max'], num=len(hist)+1)
            class_rows = []
            total = float(sum(hist))
            for label, lo, hi in classes:
                idx_lo = np.searchsorted(edges, lo, side='left')
                idx_hi = np.searchsorted(edges, hi, side='right') - 1
                idx_lo = max(0, min(idx_lo, len(hist)-1))
                idx_hi = max(0, min(idx_hi, len(hist)-1))
                count = sum(hist[idx_lo:idx_hi+1]) if idx_hi >= idx_lo else 0
                pct = (count / total * 100.0) if total > 0 else 0.0
                class_rows.append((label, int(count), pct))

            quicklook = os.path.join(out_dir, f"{base_name}_quicklook.png")
            KompsatProcessor._export_quicklook_png(ndvi_path, quicklook)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            rgb_link = f"<li>RGB: {os.path.basename(rgb_path)}</li>" if rgb_path and os.path.exists(rgb_path) else ""
            rows_html = "\n".join(
                f"<tr><td>{lbl}</td><td style='text-align:right'>{cnt:,}</td><td style='text-align:right'>{pct:.2f}%</td></tr>"
                for (lbl, cnt, pct) in class_rows
            )
            ptiles_html = " ".join([f"P{int(k)}={v:.3f}" for k, v in ptiles.items()])
            html = f"""<!doctype html>
<html lang='ko'>
<head>
  <meta charset='utf-8'/>
  <title>{title}</title>
  <style>
    body {{ font-family: 'Segoe UI', Malgun Gothic, sans-serif; margin: 24px; }}
    h1 {{ margin-bottom: 0; color: #2c3e50; }}
    .meta {{ color: #666; margin-bottom: 16px; }}
    table {{ border-collapse: collapse; width: 560px; margin-top: 10px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 10px; }}
    th {{ background: #f5f5f5; text-align: left; }}
    .small {{ color:#666; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>NDVI 결과 보고서</h1>
  <div class='meta'>생성 시각: {now}</div>
  <h2>개요</h2>
  <ul>
    <li>NDVI 파일: {os.path.basename(ndvi_path)}</li>
    {rgb_link}
    <li>좌표계: Korea 2000 (EPSG:5179)</li>
  </ul>

  <h2>통계 요약 (NoData 제외)</h2>
  <p>최솟값: {stats['min']:.4f} | 최댓값: {stats['max']:.4f} | 평균: {stats['mean']:.4f} | 표준편차: {stats['std']:.4f}</p>
  <p class='small'>분위수: {ptiles_html}</p>

  <h2>NDVI 식생 클래스 분포</h2>
  <table>
    <thead><tr><th>구간</th><th>픽셀수</th><th>비율</th></tr></thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>

  <h2>퀵룩 미리보기</h2>
  <p class='small'>상세 시각화는 QGIS에서 스타일을 적용하여 확인하세요.</p>
  <img src='{os.path.basename(quicklook)}' alt='NDVI quicklook' style='max-width:960px;border:1px solid #ddd'/>
</body>
</html>
"""
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            return html_path
        except Exception as e:
            print(f"[ERROR] 리포트 생성 실패: {str(e)}")
            return None

    def process(self):
        """전체 처리 실행 (폴더 내 다수 Aux.xml 지원)"""
        print("\n" + "=" * 70)
        print("[*] 국토정보위성 자동 처리 시작")
        print("=" * 70)
        print(f"입력 폴더: {self.input_dir}")

        xml_list = self.find_xml_files()
        if not xml_list:
            print("[ERROR] Aux.xml 파일을 찾을 수 없습니다.")
            return False

        all_success = True
        for idx, xml_path in enumerate(xml_list, 1):
            print("\n" + "-" * 70)
            print(f"데이터셋 {idx}/{len(xml_list)}: {os.path.basename(xml_path)}")
            print("-" * 70)

            self.xml_file = xml_path
            self.bands_info = {}
            self.georef_files = {}

            if not self.parse_metadata():
                all_success = False
                continue

            if not self.georeference_bands():
                all_success = False
                continue

            rgb_file = self.create_rgb_composite()
            ndvi_file = self.calculate_ndvi()

            self.generate_report(rgb_file, ndvi_file)
            if ndvi_file:
                KompsatProcessor.generate_ndvi_html_report(ndvi_file, rgb_file)

        return all_success

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("사용법: python processor.py <입력폴더경로>")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    if not os.path.isdir(input_dir):
        print(f"[ERROR] '{input_dir}' 폴더를 찾을 수 없습니다.")
        sys.exit(1)
    
    processor = KompsatProcessor(input_dir)
    try:
        success = processor.process()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[ERROR] 처리 중 예외 발생: {str(e)}")
        sys.exit(1)
