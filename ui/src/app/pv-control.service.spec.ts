import { TestBed } from '@angular/core/testing';

import { PvControlService } from './pv-control.service';

describe('ChargeControlServiceService', () => {
  let service: PvControlService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(PvControlService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
