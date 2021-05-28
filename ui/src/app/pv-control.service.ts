import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface BaseService {
  error: number;
}

export interface Meter extends BaseService {
  power_pv: number;
  power_consumption: number;
  power_grid: number;
}

export interface Wallbox extends BaseService {
  car_status?: number;
  max_current: number;
  allow_charging: boolean;
  phases_in: number;
  phases_out: number;
  power: number;
}

export enum ChargeMode {
  OFF = 'OFF',
  PV_ONLY = 'PV_ONLY',
  PV_ALL = 'PV_ALL',
  MAX = 'MAX',
  MANUAL = 'MANUAL',
}

export enum PhaseMode {
  AUTO = 'AUTO',
  CHARGE_1P = 'CHARGE_1P',
  CHARGE_3P = 'CHARGE_3P',
}

export interface ChargerController extends BaseService {
  mode: ChargeMode;
  desired_mode: ChargeMode;
  phase_mode: PhaseMode;
}

export interface Car extends BaseService {
  // data_captured_at: string; - deserialize as Date ?
  soc: number;
  cruising_range: number;
}

export interface PvControl {
  meter: Meter;
  wallbox: Wallbox;
  controller: ChargerController;
  car: Car;
}

const httpOptions = {
  // eslint-disable-next-line @typescript-eslint/naming-convention
  headers: new HttpHeaders({ 'Content-Type': 'application/json' })
};

@Injectable({
  providedIn: 'root'
})
export class PvControlService {

  constructor(private http: HttpClient) { }

  public getPvControl(): Observable<PvControl> {
    return this.http.get<PvControl>('./api/pvcontrol');
  }

  public putPvControlDesiredChargeMode(mode: ChargeMode): Observable<void> {
    // Note: explicit json converion otherwise it is sent as plain text -> 400
    return this.http.put<void>('./api/pvcontrol/controller/desired_mode', JSON.stringify(mode), httpOptions);
  }

  public putPvControlPhaseMode(mode: PhaseMode): Observable<void> {
    // Note: explicit json converion otherwise it is sent as plain text -> 400
    return this.http.put<void>('./api/pvcontrol/controller/phase_mode', JSON.stringify(mode), httpOptions);
  }
}
