import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ChargeMode, PhaseMode, PvControl, PvControlService } from './pv-control.service';

describe('PvControlServiceService', () => {
  let httpMock: HttpTestingController;
  let service: PvControlService;

  let pvControlData: PvControl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule
      ]
    });
    service = TestBed.inject(PvControlService);
    httpMock = TestBed.inject(HttpTestingController);

    pvControlData = {
      meter: {
        power_pv: 5000,
        power_consumption: 3000,
        power_grid: 2000
      },
      wallbox: {
        allow_charging: true,
        max_current: 8,
        phases_in: 3,
        phases_out: 3,
        power: 2000,
      },
      controller: {
        mode: ChargeMode.OFF,
        desired_mode: ChargeMode.PV_ONLY,
        phase_mode: PhaseMode.AUTO,
      }
    };
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should getPvControl()', () => {
    service.getPvControl().subscribe(data => {
      expect(data).toEqual(pvControlData);
    });
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
  });

  it('should putPvControlDesiredChargeMode()', () => {
    service.putPvControlDesiredChargeMode(ChargeMode.PV_ONLY).subscribe();

    const req = httpMock.expectOne('./api/pvcontrol/controller/desired_mode');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe('"PV_ONLY"');
    req.flush(null);
  });

  it('should putPvControlPhaseMode()', () => {
    service.putPvControlPhaseMode(PhaseMode.CHARGE_1P).subscribe();

    const req = httpMock.expectOne('./api/pvcontrol/controller/phase_mode');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe('"CHARGE_1P"');
    req.flush(null);
  });
});
